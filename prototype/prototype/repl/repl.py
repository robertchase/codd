"""REPL loop: read-lex-parse-execute-display."""

from __future__ import annotations

import readline  # noqa: F401 — import enables line editing and history for input()

from prototype.data.sample import load_sample_data
from prototype.executor.environment import Environment
from prototype.executor.executor import Executor, ExecutionError
from prototype.lexer.lexer import Lexer, LexError
from prototype.model.relation import Relation
from prototype.parser.parser import Parser, ParseError
from prototype.repl.formatter import format_array, format_relation


def run_repl(env: Environment | None = None) -> None:
    """Run the interactive REPL."""
    if env is None:
        env = Environment()

    executor = Executor(env)

    print("Codd prototype REPL")
    print("Commands: \\load (load sample data), \\env (show bindings), \\quit (exit)")
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
    cmd = line.split()[0].lower()
    if cmd == "\\quit" or cmd == "\\q":
        raise SystemExit(0)
    elif cmd == "\\load":
        load_sample_data(env)
        print("Loaded: E (Employee), D (Department), Phone, ContractorPay")
    elif cmd == "\\env":
        names = env.names()
        if not names:
            print("(no relations loaded)")
        else:
            for name in names:
                rel = env.lookup(name)
                print(f"  {name}: {len(rel)} tuples, attrs: {sorted(rel.attributes)}")
    else:
        print(f"Unknown command: {cmd}")
