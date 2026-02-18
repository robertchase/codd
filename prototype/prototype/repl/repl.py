"""REPL loop: read-lex-parse-execute-display."""

from __future__ import annotations

import readline  # noqa: F401 — import enables line editing and history for input()
from pathlib import Path

from prototype.data.loader import LoadError, load_csv
from prototype.data.sample import load_sample_data
from prototype.data.workspace import is_workspace_file, load_workspace, save_workspace
from prototype.executor.environment import Environment
from prototype.executor.executor import Executor, ExecutionError
from prototype.lexer.lexer import Lexer, LexError
from prototype.model.relation import Relation
from prototype.parser import ast_nodes as ast
from prototype.parser.parser import Parser, ParseError
from prototype.repl.formatter import format_array, format_relation

# Tracks the last-used save path for \save with no args.
_last_save_path: Path | None = None


def run_repl(env: Environment | None = None) -> None:
    """Run the interactive REPL."""
    if env is None:
        env = Environment()

    executor = Executor(env)

    print("Codd prototype REPL")
    print(
        "Commands: \\load [file], \\save [file], \\drop <name>, "
        "\\env, \\quit"
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

        try:
            tokens = Lexer(line).tokenize()
            tree = Parser(tokens).parse()
            result = executor.execute(tree)

            if isinstance(tree, ast.Assignment):
                print(f"{tree.name} := ", end="")
            if isinstance(result, list):
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
    else:
        print(f"Unknown command: {cmd}")


def _cmd_load(args: list[str], env: Environment) -> None:
    """Handle \\load: load sample data, a CSV file, or a workspace file."""
    if not args:
        load_sample_data(env)
        print("Loaded: E (Employee), D (Department), Phone, ContractorPay")
        return

    # Parse options: --as=Name, --genkey, --genkey=Name.
    file_arg = None
    alias = None
    genkey: str | None = None
    genkey_seen = False
    for arg in args:
        if arg.startswith("--as="):
            alias = arg[len("--as="):]
        elif arg == "--genkey":
            genkey_seen = True
        elif arg.startswith("--genkey="):
            genkey_seen = True
            genkey = arg[len("--genkey="):]
        elif file_arg is None:
            file_arg = arg
        else:
            print(f"Error: unexpected argument: {arg}")
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
            print("Error: --as cannot be used with workspace files")
            return
        if genkey_seen:
            print("Error: --genkey cannot be used with workspace files")
            return
        _load_workspace_file(path, env)
    else:
        # Resolve genkey name: explicit name, or derive from relation name.
        if genkey_seen and genkey is None:
            genkey = alias if alias else path.stem
        _load_csv_file(path, env, alias, genkey)


def _load_csv_file(
    path: Path,
    env: Environment,
    alias: str | None,
    genkey: str | None = None,
) -> None:
    """Load a CSV file into the environment."""
    name = alias if alias else path.stem
    try:
        with open(path) as f:
            rel = load_csv(f, name, genkey=genkey)
        env.bind(name, rel)
        print(f"Loaded {name}: {len(rel)} tuples, attrs: {sorted(rel.attributes)}")
    except LoadError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Error loading {path}: {e}")


def _load_workspace_file(path: Path, env: Environment) -> None:
    """Load a .codd workspace file into the environment."""
    global _last_save_path
    try:
        relations = load_workspace(path)
        for name, rel in relations.items():
            env.bind(name, rel)
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
