"""CLI entry point for codd."""

import os
import pathlib
import re
import sys

import click

from codd import __version__
from codd.data.loader import load_csv
from codd.executor.environment import Environment


@click.command()
@click.version_option(version=__version__, prog_name="codd")
@click.argument("files", nargs=-1, type=click.Path())
@click.option(
    "-e",
    "--expr",
    "expression",
    default=None,
    help="Evaluate expression and exit (omit for REPL).",
)
@click.option(
    "-f",
    "--file",
    "script_file",
    default=None,
    type=click.Path(exists=True),
    help="Evaluate expressions from a file and exit.",
)
@click.option(
    "--arg",
    "args",
    multiple=True,
    help="Substitute {{name}} in -f scripts: --arg name=value.",
)
@click.option(
    "--init",
    "init_files",
    multiple=True,
    type=click.Path(exists=True),
    help="Run codd file(s) as setup before anything else (repeatable).",
)
@click.option(
    "--sample", "sample", is_flag=True, default=False,
    help="Load sample data (E, D, Phone, ContractorPay).",
)
@click.option(
    "--load", "auto_load", is_flag=True, default=False,
    help="Load sample data (alias for --sample).",
)
@click.option(
    "--genkey", is_flag=True, default=False,
    help="Generate synthetic {relation}_id key column for each loaded file.",
)
@click.option(
    "--csv", "output_csv", is_flag=True, default=False,
    help="Output as CSV instead of table (only with -e/-f).",
)
@click.option(
    "--no-header", "no_header", is_flag=True, default=False,
    help="Omit header row from CSV output (implies --csv).",
)
@click.option(
    "--ops", "show_ops", is_flag=True, default=False,
    help="Print language primitives reference and exit.",
)
def main(
    files: tuple[str, ...],
    expression: str | None,
    script_file: str | None,
    args: tuple[str, ...],
    init_files: tuple[str, ...],
    sample: bool,
    auto_load: bool,
    genkey: bool,
    output_csv: bool,
    no_header: bool,
    show_ops: bool,
) -> None:
    """Codd relational algebra.

    Load CSV files and either evaluate an expression (-e), run a script (-f),
    or start a REPL. Use name=path.csv to load a file with an explicit
    relation name. Use --init to run setup scripts before anything else.

    \b
    Examples:
        codd prices.csv                            # REPL with prices loaded
        codd prices.csv -e "prices ? price > 100"  # evaluate and exit
        codd prices.csv -f query.codd --arg min=50 # run script with args
        codd p=prices.csv --csv -e "p $ price"     # CSV output
        codd --init types.codd -f main.codd        # setup then script
        codd --ops                                  # print reference
        cat data.csv | codd - -e "stdin"            # pipe stdin
    """
    if expression is not None and script_file is not None:
        raise click.ClickException("Cannot use both -e and -f")
    if args and script_file is None:
        raise click.ClickException("--arg requires -f")
    if show_ops:
        from codd.cli.ops_cmd import ops_output

        click.echo(ops_output())
        return

    env = Environment()
    stdin_consumed = False
    load_sample = sample or auto_load

    # Run --init files first so type/alias definitions are in place before
    # any positional loads (which may reference them via ::schema.csv) and
    # before -e/-f scripts run.
    for init_path in init_files:
        try:
            text = pathlib.Path(init_path).read_text()
        except OSError as e:
            raise click.ClickException(f"--init: cannot read {init_path}: {e}")
        source = pathlib.Path(init_path).resolve()
        _execute_codd_source(
            text, env, source, including=frozenset({source}),
        )

    if load_sample:
        from codd.data.sample import load_sample_data

        load_sample_data(env)
        if expression is None and script_file is None:
            click.echo("Sample data loaded: E, D, Phone, ContractorPay")

    def _parse_file_arg(
        arg: str,
    ) -> tuple[str | None, str, str | None, str | None, str | None]:
        """Parse a file argument into (name, path, genkey, genuuid_col, genhash_col).

        Supports +key, +key=Col, +uuid=Col, +hash=Col suffixes and n=path prefix.
        """
        name: str | None = None
        rest = arg
        file_genkey: str | None = None
        genuuid_col: str | None = None
        genhash_col: str | None = None

        # Strip +hash=Col suffix first.
        if "+hash=" in rest:
            idx = rest.index("+hash=")
            genhash_col = rest[idx + 6:]
            rest = rest[:idx]

        # Strip +uuid=Col suffix.
        if "+uuid=" in rest:
            idx = rest.index("+uuid=")
            genuuid_col = rest[idx + 6:]
            rest = rest[:idx]

        # Strip +key or +key=Name suffix (before name= split).
        if "+key" in rest:
            idx = rest.index("+key")
            suffix = rest[idx + 4:]  # after "+key"
            rest = rest[:idx]
            if suffix.startswith("="):
                file_genkey = suffix[1:]  # explicit key name
            else:
                file_genkey = ""  # sentinel: use default name

        # Split name=path if present.
        if "=" in rest:
            name, rest = rest.split("=", 1)

        return name, rest, file_genkey, genuuid_col, genhash_col

    def _resolve_genkey(
        name: str, file_genkey: str | None
    ) -> tuple[str | None, str | None]:
        """Resolve genkey params for a file.

        Returns (genkey, genkey_col):
        - genkey: passed to loader (appends _id)
        - genkey_col: exact column name (overrides genkey)

        Per-file +key takes precedence over global --genkey.
        """
        if file_genkey is not None:
            if file_genkey:
                # Explicit name: +key=n → column is exactly "n"
                return (None, file_genkey)
            # Default: +key → column is {name}_id
            return (name, None)
        if genkey:
            return (name, None)
        return (None, None)

    # Load positional files (stem becomes name, - means stdin).
    # Supports name=path and +key syntax.
    for filepath in files:
        alias, path, file_gk, file_uuid, file_hash = _parse_file_arg(filepath)
        if path == "-":
            stdin_consumed = True
            rel_name = alias or "stdin"
            gk, gk_col = _resolve_genkey(rel_name, file_gk)
            _load_stdin(env, rel_name, genkey=gk, genkey_col=gk_col,
                        genuuid_col=file_uuid, genhash_col=file_hash)
        else:
            rel_name = alias or pathlib.Path(path).stem
            gk, gk_col = _resolve_genkey(rel_name, file_gk)
            _load_file(env, path, rel_name, genkey=gk, genkey_col=gk_col,
                       genuuid_col=file_uuid, genhash_col=file_hash)

    # Auto-load stdin if piped and not already consumed
    if not stdin_consumed and not sys.stdin.isatty():
        gk, gk_col = _resolve_genkey("stdin", None)
        _load_stdin(env, "stdin", genkey=gk, genkey_col=gk_col)
        stdin_consumed = True

    if no_header:
        output_csv = True

    if expression is not None:
        # Eval mode: evaluate and exit.
        _run_eval(expression, env, output_csv, no_header)
    elif script_file is not None:
        # File mode: run script and exit.
        _run_file(script_file, args, env, output_csv, no_header)
    else:
        # REPL mode.
        _enter_repl(env, stdin_consumed)


def _run_eval(
    expression: str, env: Environment, output_csv: bool, no_header: bool = False
) -> None:
    """Evaluate a single expression and print the result."""
    from codd.executor.executor import Executor, ExecutionError
    from codd.lexer.lexer import Lexer, LexError
    from codd.model.relation import Relation
    from codd.model.types import RotatedArray
    from codd.parser.parser import Parser, ParseError
    from codd.repl.formatter import (
        format_array,
        format_array_csv,
        format_csv,
        format_relation,
        format_rotated,
    )

    from codd.parser import ast_nodes as ast

    # Bash history expansion escapes '!' to '\!'.
    expression = expression.replace("\\!", "!")

    # Backslash commands (\export, \load, etc.) work in -e just like in -f,
    # but with quiet=False so output (e.g. "Exported N rows") is shown.
    if expression.lstrip().startswith("\\"):
        _run_script_command(expression.lstrip(), env, quiet=False)
        return

    header = not no_header

    try:
        tokens = Lexer(expression).tokenize()
        tree = Parser(tokens).parse()
        result = Executor(env).execute(tree)

        # Assignments are silent in non-REPL mode.
        if isinstance(tree, ast.Assignment):
            return

        if isinstance(result, RotatedArray):
            click.echo(format_rotated(result))
        elif isinstance(result, list):
            output = (
                format_array_csv(result, header=header)
                if output_csv else format_array(result)
            )
            if output:
                click.echo(output)
        elif isinstance(result, Relation):
            output = (
                format_csv(result, header=header)
                if output_csv else format_relation(result)
            )
            if output:
                click.echo(output)
        else:
            click.echo(result)
    except (LexError, ParseError, ExecutionError) as e:
        raise click.ClickException(str(e))


def _substitute_args(text: str, args: tuple[str, ...]) -> str:
    """Replace {{name}} placeholders with --arg values.

    Raises click.ClickException for malformed --arg values or
    unresolved placeholders.
    """
    arg_map: dict[str, str] = {}
    for arg in args:
        if "=" not in arg:
            raise click.ClickException(
                f"Invalid --arg format: {arg!r} (expected name=value)"
            )
        name, value = arg.split("=", 1)
        arg_map[name.strip()] = value.strip()

    def _replace(m: re.Match) -> str:
        name = m.group(1)
        if name not in arg_map:
            return m.group(0)  # leave unresolved for error check below
        return arg_map[name]

    result = re.sub(r"\{\{(\w+)\}\}", _replace, text)

    # Check for unresolved placeholders.
    missing = re.findall(r"\{\{(\w+)\}\}", result)
    if missing:
        raise click.ClickException(
            f"Missing --arg for placeholder(s): {', '.join(sorted(set(missing)))}"
        )

    return result


def _execute_codd_source(
    text: str,
    env: Environment,
    source_path: pathlib.Path | None,
    *,
    including: frozenset[pathlib.Path] | None = None,
) -> tuple[object, bool]:
    """Execute codd source text against *env*.

    Returns ``(last_result, last_was_assignment)``.  Does not print anything.

    *source_path* is the resolved absolute path of the source file, used for
    relative-path resolution in ``\\include``.  Pass ``None`` for text that
    did not come from a file (e.g. the REPL or ``-e``).

    *including* is the set of currently-including source paths for cycle
    detection; each call down the ``\\include`` chain extends it.
    """
    from codd.executor.executor import Executor, ExecutionError
    from codd.lexer.lexer import Lexer, LexError
    from codd.parser.parser import Parser, ParseError

    from codd.repl.continuation import join_continuation
    from codd.parser import ast_nodes as ast

    lines = [
        line.strip()
        for line in join_continuation(text.splitlines())
        if line.strip() and not line.strip().startswith("#")
    ]

    executor = Executor(env)
    result: object = None
    last_was_assignment = False

    try:
        for line in lines:
            line = line.replace("\\!", "!")
            if line.startswith("\\"):
                _run_script_command(
                    line, env,
                    base_dir=(source_path.parent if source_path else None),
                    including=including,
                )
                last_was_assignment = False
                continue
            tokens = Lexer(line).tokenize()
            tree = Parser(tokens).parse()
            result = executor.execute(tree)
            last_was_assignment = isinstance(tree, ast.Assignment)
    except (LexError, ParseError, ExecutionError) as e:
        raise click.ClickException(str(e))

    return result, last_was_assignment


def _run_file(
    script_file: str,
    args: tuple[str, ...],
    env: Environment,
    output_csv: bool,
    no_header: bool = False,
) -> None:
    """Execute expressions from a script file.

    Each non-blank, non-comment line is executed sequentially.
    Assignments accumulate in the environment. The last line's
    result is printed.
    """
    from codd.model.relation import Relation
    from codd.model.types import RotatedArray
    from codd.repl.formatter import (
        format_array,
        format_array_csv,
        format_csv,
        format_relation,
        format_rotated,
    )

    try:
        with open(script_file) as f:
            text = f.read()
    except OSError as e:
        raise click.ClickException(f"Cannot read {script_file}: {e}")

    text = _substitute_args(text, args)
    source_path = pathlib.Path(script_file).resolve()

    result, last_was_assignment = _execute_codd_source(
        text, env, source_path, including=frozenset({source_path}),
    )

    # Print the last result (assignments are silent).
    if last_was_assignment:
        return
    if isinstance(result, RotatedArray):
        click.echo(format_rotated(result))
        return
    header = not no_header
    if isinstance(result, list):
        output = (
            format_array_csv(result, header=header)
            if output_csv else format_array(result)
        )
        if output:
            click.echo(output)
    elif isinstance(result, Relation):
        output = (
            format_csv(result, header=header)
            if output_csv else format_relation(result)
        )
        if output:
            click.echo(output)
    elif result is not None:
        click.echo(result)


def _run_script_command(
    line: str,
    env: Environment,
    quiet: bool = True,
    *,
    base_dir: pathlib.Path | None = None,
    including: frozenset[pathlib.Path] | None = None,
) -> None:
    """Handle a backslash command inside a -f script or -e expression.

    Supports \\load, \\export, and \\include.  Other commands are ignored
    with a warning.  *quiet* suppresses success messages; defaults to True
    for -f scripts, pass False for interactive -e use.

    *base_dir* is the directory of the calling script, used to resolve
    relative paths in ``\\include``.  *including* is the set of
    currently-including file paths, for cycle detection.
    """
    parts = line.split()
    cmd = parts[0].lower()
    args = parts[1:]

    if cmd == "\\load":
        from codd.repl.repl import _cmd_load

        _cmd_load(args, env, quiet=quiet)
    elif cmd == "\\export":
        from codd.repl.repl import _cmd_export

        _cmd_export(args, env, quiet=quiet)
    elif cmd == "\\include":
        _cmd_include(args, env, base_dir=base_dir, including=including)
    elif cmd in ("\\quit", "\\q"):
        raise SystemExit(0)
    else:
        click.echo(f"Warning: command {cmd} not supported in scripts, skipping")


def _cmd_include(
    args: list[str],
    env: Environment,
    *,
    base_dir: pathlib.Path | None = None,
    including: frozenset[pathlib.Path] | None = None,
) -> None:
    """Handle \\include: execute another codd file in the current environment.

    Relative paths resolve against *base_dir* (the directory of the calling
    script) if provided; otherwise against the current working directory.
    """
    if len(args) != 1:
        raise click.ClickException("Usage: \\include <file>")

    raw = args[0]
    p = pathlib.Path(raw)
    if not p.is_absolute():
        root = base_dir if base_dir is not None else pathlib.Path.cwd()
        p = root / p
    p = p.resolve()

    if including and p in including:
        raise click.ClickException(f"\\include: cycle detected at {p}")

    try:
        text = p.read_text()
    except OSError as e:
        raise click.ClickException(f"\\include: cannot read {p}: {e}")

    new_including = (including or frozenset()) | {p}
    _execute_codd_source(text, env, p, including=new_including)


def _enter_repl(env: Environment, stdin_consumed: bool) -> None:
    """Enter the interactive REPL."""
    from codd.repl.repl import run_repl

    # If stdin was consumed for data, reopen fd 0 from the terminal
    # so the REPL can still read interactive input with readline history.
    if stdin_consumed:
        try:
            tty_fd = os.open("/dev/tty", os.O_RDONLY)
            os.dup2(tty_fd, 0)
            os.close(tty_fd)
            sys.stdin = open(0, closefd=False)
            # Python sets stdout to fully-buffered when stdin is a pipe.
            # Now that stdin is a terminal again, restore line buffering
            # so output (prompts, "Loaded:" messages) appears immediately.
            sys.stdout.reconfigure(line_buffering=True)
        except OSError:
            raise click.ClickException(
                "Cannot reopen terminal for interactive input after reading stdin"
            )

    if env.names():
        click.echo(f"Loaded: {', '.join(env.names())}")

    run_repl(env)


def _load_file(
    env: Environment,
    filepath: str,
    name: str,
    *,
    genkey: str | None = None,
    genkey_col: str | None = None,
    genuuid_col: str | None = None,
    genhash_col: str | None = None,
) -> None:
    """Load a CSV file into the environment."""
    try:
        with open(filepath) as f:
            rel = load_csv(f, name, genkey=genkey, genkey_col=genkey_col,
                           genuuid_col=genuuid_col, genhash_col=genhash_col)
        env.bind(name, rel)
    except OSError as e:
        raise click.ClickException(f"Cannot read {filepath}: {e}")


def _load_stdin(
    env: Environment,
    name: str,
    *,
    genkey: str | None = None,
    genkey_col: str | None = None,
    genuuid_col: str | None = None,
    genhash_col: str | None = None,
) -> None:
    """Load CSV data from stdin into the environment."""
    if sys.stdin.isatty():
        raise click.ClickException("stdin requested but no data piped")
    rel = load_csv(sys.stdin, name, genkey=genkey, genkey_col=genkey_col,
                   genuuid_col=genuuid_col, genhash_col=genhash_col)
    env.bind(name, rel)
