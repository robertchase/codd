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
    relation name.

    \b
    Examples:
        codd prices.csv                            # REPL with prices loaded
        codd prices.csv -e "prices ? price > 100"  # evaluate and exit
        codd prices.csv -f query.codd --arg min=50 # run script with args
        codd p=prices.csv --csv -e "p $ price"     # CSV output
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

    if load_sample:
        from codd.data.sample import load_sample_data

        load_sample_data(env)
        if expression is None:
            click.echo("Sample data loaded: E, D, Phone, ContractorPay")

    def _genkey_for(name: str) -> str | None:
        """Resolve the genkey name for a relation."""
        return name if genkey else None

    # Load positional files (stem becomes name, - means stdin).
    # Supports name=path syntax for explicit naming: p=prices.csv
    for filepath in files:
        if filepath == "-":
            stdin_consumed = True
            _load_stdin(env, "stdin", genkey=_genkey_for("stdin"))
        elif "=" in filepath:
            name, path = filepath.split("=", 1)
            if path == "-":
                stdin_consumed = True
                _load_stdin(env, name, genkey=_genkey_for(name))
            else:
                _load_file(env, path, name, genkey=_genkey_for(name))
        else:
            p = pathlib.Path(filepath)
            name = p.stem
            _load_file(env, filepath, name, genkey=_genkey_for(name))

    # Auto-load stdin if piped and not already consumed
    if not stdin_consumed and not sys.stdin.isatty():
        _load_stdin(env, "stdin", genkey=_genkey_for("stdin"))
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
    from codd.parser.parser import Parser, ParseError
    from codd.repl.formatter import (
        format_array,
        format_array_csv,
        format_csv,
        format_relation,
    )

    # Bash history expansion escapes '!' to '\!'.
    expression = expression.replace("\\!", "!")
    header = not no_header

    try:
        tokens = Lexer(expression).tokenize()
        tree = Parser(tokens).parse()
        result = Executor(env).execute(tree)

        if isinstance(result, list):
            click.echo(
                format_array_csv(result, header=header)
                if output_csv else format_array(result)
            )
        elif isinstance(result, Relation):
            click.echo(
                format_csv(result, header=header)
                if output_csv else format_relation(result)
            )
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
    from codd.executor.executor import Executor, ExecutionError
    from codd.lexer.lexer import Lexer, LexError
    from codd.model.relation import Relation
    from codd.parser.parser import Parser, ParseError
    from codd.repl.formatter import (
        format_array,
        format_array_csv,
        format_csv,
        format_relation,
    )

    try:
        with open(script_file) as f:
            text = f.read()
    except OSError as e:
        raise click.ClickException(f"Cannot read {script_file}: {e}")

    text = _substitute_args(text, args)

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    if not lines:
        raise click.ClickException(f"No expressions in {script_file}")

    executor = Executor(env)
    result = None

    try:
        for line in lines:
            line = line.replace("\\!", "!")
            tokens = Lexer(line).tokenize()
            tree = Parser(tokens).parse()
            result = executor.execute(tree)

        # Print the last result.
        header = not no_header
        if isinstance(result, list):
            click.echo(
                format_array_csv(result, header=header)
                if output_csv else format_array(result)
            )
        elif isinstance(result, Relation):
            click.echo(
                format_csv(result, header=header)
                if output_csv else format_relation(result)
            )
        elif result is not None:
            click.echo(result)
    except (LexError, ParseError, ExecutionError) as e:
        raise click.ClickException(str(e))


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
    env: Environment, filepath: str, name: str, *, genkey: str | None = None
) -> None:
    """Load a CSV file into the environment."""
    try:
        with open(filepath) as f:
            rel = load_csv(f, name, genkey=genkey)
        env.bind(name, rel)
    except OSError as e:
        raise click.ClickException(f"Cannot read {filepath}: {e}")


def _load_stdin(env: Environment, name: str, *, genkey: str | None = None) -> None:
    """Load CSV data from stdin into the environment."""
    if sys.stdin.isatty():
        raise click.ClickException("stdin requested but no data piped")
    rel = load_csv(sys.stdin, name, genkey=genkey)
    env.bind(name, rel)
