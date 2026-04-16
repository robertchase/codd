"""REPL loop: read-lex-parse-execute-display."""

from __future__ import annotations

from pathlib import Path

from codd.data.loader import LoadError, load_csv
from codd.data.sample import load_sample_data
from codd.data.workspace import is_workspace_file, load_workspace, save_workspace
from codd.executor.environment import Environment
from codd.executor.executor import Executor, ExecutionError
from codd.lexer.lexer import Lexer, LexError
from codd.model.relation import Relation
from codd.parser import ast_nodes as ast
from codd.parser.parser import Parser, ParseError
from codd.cli.ops_cmd import ops_output
from codd.model.types import RotatedArray
from codd.repl.formatter import (
    format_array,
    format_array_csv,
    format_csv,
    format_relation,
    format_rotated,
)

# Tracks the last-used save path for \save with no args.
_last_save_path: Path | None = None


def run_repl(env: Environment | None = None) -> None:
    """Run the interactive REPL."""
    # Lazy import: readline must initialize after stdin is a real terminal.
    # When stdin starts as a pipe (e.g. cat file | repl --as x=-), importing
    # readline early leaves it unable to detect terminal capabilities.
    import readline  # noqa: F401 — enables line editing and history for input()

    if env is None:
        env = Environment()

    executor = Executor(env)

    from codd import __version__

    print(f"Codd REPL v{__version__}")
    print(
        "Commands: \\load <file> [:: Schema] [name], \\save [file], \\export <file> <expr>, "
        "\\drop <name>, \\env, \\ops, \\quit"
    )
    print()

    while True:
        try:
            line = input("codd> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        if line.startswith("\\"):
            _handle_command(line, env)
            continue

        # Line continuation: accumulate lines ending with backslash.
        while line.rstrip().endswith("\\"):
            line = line.rstrip()[:-1]
            try:
                line += input("....> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                line = ""
                break

        if not line:
            continue

        try:
            tokens = Lexer(line).tokenize()
            tree = Parser(tokens).parse()
            result = executor.execute(tree)

            if isinstance(tree, ast.Assignment):
                # Assignments bind silently; just confirm the name and size.
                if isinstance(result, Relation):
                    print(f"{tree.name} := ({len(result)} tuples)")
                else:
                    print(f"{tree.name} := (assigned)")
            elif isinstance(result, RotatedArray):
                print(format_rotated(result))
            elif isinstance(result, list):
                print(format_array(result))
            elif isinstance(result, Relation):
                print(format_relation(result))
            else:
                print(result)
        except (LexError, ParseError, ExecutionError) as e:
            print(f"Error: {e}")
        except Exception as e:
            print(f"Internal error: {e}")

        print()


def _handle_command(line: str, env: Environment) -> None:
    """Handle REPL meta-commands."""
    parts = line.split()
    cmd = parts[0].lower()
    args = parts[1:]

    if cmd in ("\\quit", "\\q"):
        raise SystemExit(0)
    elif cmd == "\\load":
        _cmd_load(args, env)
    elif cmd == "\\save":
        _cmd_save(args, env)
    elif cmd == "\\drop":
        _cmd_drop(args, env)
    elif cmd == "\\env":
        _cmd_env(env)
    elif cmd == "\\export":
        _cmd_export(args, env)
    elif cmd == "\\ops":
        if args:
            from codd.cli.ops_cmd import ops_detail

            detail = ops_detail(args[0])
            if detail:
                print(detail)
            else:
                print(f"No detail available for {args[0]!r}")
        else:
            print(ops_output())
    else:
        print(f"Unknown command: {cmd}")


def _cmd_load(args: list[str], env: Environment, *, quiet: bool = False) -> None:
    """Handle \\load: load sample data, a CSV file, or a workspace file.

    Syntax: \\load file [:: SchemaName] [name] [--genkey[=Name]] [+key=Col] [+uuid=Col]

    When *quiet* is True, success messages are suppressed (errors still print).
    """
    if not args:
        load_sample_data(env)
        if not quiet:
            print("Loaded: E (Employee), D (Department), Phone, ContractorPay")
        return

    # Parse options: --genkey, --genkey=Name, +key=Col, +uuid=Col, :: SchemaName.
    # Positional: file [:: SchemaName] [name]
    file_arg = None
    alias = None
    schema_name: str | None = None
    genkey: str | None = None
    genkey_seen = False
    genkey_col: str | None = None
    genuuid_col: str | None = None
    genhash_col: str | None = None
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--genkey":
            genkey_seen = True
        elif arg.startswith("--genkey="):
            genkey_seen = True
            genkey = arg[len("--genkey="):]
        elif arg.startswith("+key="):
            genkey_col = arg[len("+key="):]
        elif arg.startswith("+uuid="):
            genuuid_col = arg[len("+uuid="):]
        elif arg.startswith("+hash="):
            genhash_col = arg[len("+hash="):]
        elif arg == "::" and i + 1 < len(args):
            i += 1
            schema_name = args[i]
        elif file_arg is None:
            file_arg = arg
        elif alias is None:
            alias = arg
        else:
            print(f"Error: unexpected argument: {arg}")
            return
        i += 1

    if genkey_seen and genkey_col is not None:
        print("Error: --genkey and +key= cannot be used together")
        return

    if file_arg is None:
        print("Error: \\load requires a filename")
        return

    path = Path(file_arg)
    if not path.exists():
        print(f"Error: file not found: {path}")
        return

    if is_workspace_file(path):
        if alias:
            print("Error: name cannot be used with workspace files")
            return
        if genkey_seen:
            print("Error: --genkey cannot be used with workspace files")
            return
        if genkey_col is not None:
            print("Error: +key= cannot be used with workspace files")
            return
        if genuuid_col is not None:
            print("Error: +uuid= cannot be used with workspace files")
            return
        if genhash_col is not None:
            print("Error: +hash= cannot be used with workspace files")
            return
        if schema_name:
            print("Error: :: schema cannot be used with workspace files")
            return
        _load_workspace_file(path, env, quiet=quiet)
    else:
        # Resolve genkey name: explicit name, or derive from relation name.
        if genkey_seen and genkey is None:
            genkey = alias if alias else path.stem
        _load_csv_file(path, env, alias, genkey, schema_name, genkey_col,
                       genuuid_col=genuuid_col, genhash_col=genhash_col,
                       quiet=quiet)


def _load_csv_file(
    path: Path,
    env: Environment,
    alias: str | None,
    genkey: str | None = None,
    schema_name: str | None = None,
    genkey_col: str | None = None,
    genuuid_col: str | None = None,
    genhash_col: str | None = None,
    quiet: bool = False,
) -> None:
    """Load a CSV file into the environment, optionally applying a schema."""
    name = alias if alias else path.stem
    try:
        with open(path) as f:
            rel = load_csv(f, name, genkey=genkey, genkey_col=genkey_col,
                           genuuid_col=genuuid_col, genhash_col=genhash_col)
        if schema_name:
            from codd.model.coerce import (
                CoercionError,
                apply_schema,
                schema_from_relation,
            )

            try:
                schema_rel = env.lookup(schema_name)
            except KeyError:
                print(f"Error: unknown schema relation: {schema_name!r}")
                return
            try:
                schema_dict = schema_from_relation(schema_rel)
                rel = apply_schema(rel, schema_dict, env=env)
            except CoercionError as e:
                print(f"Error applying schema: {e}")
                return
        env.bind(name, rel)
        if not quiet:
            print(f"Loaded {name}: {len(rel)} tuples, attrs: {sorted(rel.attributes)}")
    except LoadError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Error loading {path}: {e}")


def _load_workspace_file(
    path: Path, env: Environment, *, quiet: bool = False
) -> None:
    """Load a .codd workspace file into the environment."""
    global _last_save_path
    try:
        relations = load_workspace(path)
        for name, rel in relations.items():
            env.bind(name, rel)
        if not quiet:
            names = sorted(relations.keys())
            print(f"Loaded workspace: {', '.join(names)}")
        _last_save_path = path
    except Exception as e:
        print(f"Error loading workspace {path}: {e}")


def _cmd_save(args: list[str], env: Environment) -> None:
    """Handle \\save: save workspace to a .codd file."""
    global _last_save_path

    if args:
        path = Path(args[0])
    elif _last_save_path is not None:
        path = _last_save_path
    else:
        print("Error: \\save requires a filename (no previous save path)")
        return

    try:
        save_workspace(env, path)
        _last_save_path = path
        print(f"Saved workspace to {path}")
    except Exception as e:
        print(f"Error saving workspace: {e}")


def _cmd_export(args: list[str], env: Environment, *, quiet: bool = False) -> None:
    """Handle \\export: export a relation to a CSV file.

    Usage: \\export <file> <expr>
    The expression is evaluated and the result is written as CSV.

    When *quiet* is True, success messages are suppressed (errors still print).
    """
    if len(args) < 2:
        print("Usage: \\export <file> <expression>")
        return

    path = Path(args[0])
    expr_str = " ".join(args[1:])

    try:
        tokens = Lexer(expr_str).tokenize()
        tree = Parser(tokens).parse()
        result = Executor(env).execute(tree)
    except (LexError, ParseError, ExecutionError) as e:
        print(f"Error: {e}")
        return

    if isinstance(result, list):
        csv_text = format_array_csv(result)
    elif isinstance(result, Relation):
        csv_text = format_csv(result)
    else:
        print(f"Error: cannot export {type(result).__name__} (expected a relation)")
        return

    try:
        path.write_text(csv_text + "\n")
        if not quiet:
            count = len(result)
            print(f"Exported {count} rows to {path}")
    except OSError as e:
        print(f"Error writing {path}: {e}")


def _cmd_drop(args: list[str], env: Environment) -> None:
    """Handle \\drop: remove a relation from the environment."""
    if not args:
        print("Error: \\drop requires a relation name")
        return

    name = args[0]
    try:
        env.unbind(name)
        print(f"Dropped {name}")
    except KeyError:
        print(f"Error: unknown relation: {name!r}")


def _cmd_env(env: Environment) -> None:
    """Handle \\env: show all relation bindings."""
    names = env.names()
    if not names:
        print("(no relations loaded)")
    else:
        for name in names:
            rel = env.lookup(name)
            print(f"  {name}: {len(rel)} tuples, attrs: {sorted(rel.attributes)}")
