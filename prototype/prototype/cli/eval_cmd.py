"""CLI subcommand: eval."""

import pathlib
import sys

import click

from prototype.data.loader import load_csv
from prototype.data.sample import load_sample_data
from prototype.executor.environment import Environment
from prototype.executor.executor import Executor, ExecutionError
from prototype.lexer.lexer import Lexer, LexError
from prototype.model.relation import Relation
from prototype.parser.parser import Parser, ParseError
from prototype.repl.formatter import format_array, format_relation


@click.command("eval")
@click.argument("expression")
@click.argument("files", nargs=-1, type=click.Path())
@click.option(
    "--as",
    "aliases",
    multiple=True,
    help="Bind a file with an explicit name: --as name=path.csv",
)
@click.option(
    "--sample", is_flag=True, default=False, help="Load sample data (E, D, Phone, ContractorPay)"
)
@click.option(
    "--genkey",
    is_flag=True,
    default=False,
    help="Generate synthetic {relation}_id key column for each loaded file.",
)
def eval_cmd(
    expression: str,
    files: tuple[str, ...],
    aliases: tuple[str, ...],
    sample: bool,
    genkey: bool,
) -> None:
    """Evaluate a single expression and print the result.

    Load CSV files as relations. By default, the file stem (without extension)
    is used as the relation name. Use --as name=path.csv for explicit naming.
    Use - or --as name=- to read from stdin.

    If stdin is not a TTY and no explicit stdin binding was requested,
    it is loaded as a relation named 'stdin'.
    """
    env = Environment()
    stdin_consumed = False

    if sample:
        load_sample_data(env)

    def _genkey_for(name: str) -> str | None:
        """Resolve the genkey name for a relation."""
        return name if genkey else None

    # Load aliased files (- means stdin)
    for alias in aliases:
        if "=" not in alias:
            raise click.ClickException(f"Invalid --as format: {alias!r} (expected name=path)")
        name, path = alias.split("=", 1)
        name = name.strip()
        path = path.strip()
        if path == "-":
            stdin_consumed = True
            _load_stdin(env, name, genkey=_genkey_for(name))
        else:
            _load_file(env, path, name, genkey=_genkey_for(name))

    # Load positional files (stem becomes name, - means stdin)
    for filepath in files:
        if filepath == "-":
            stdin_consumed = True
            _load_stdin(env, "stdin", genkey=_genkey_for("stdin"))
        else:
            p = pathlib.Path(filepath)
            name = p.stem
            _load_file(env, filepath, name, genkey=_genkey_for(name))

    # Auto-load stdin if piped and not already consumed
    if not stdin_consumed and not sys.stdin.isatty():
        _load_stdin(env, "stdin", genkey=_genkey_for("stdin"))

    try:
        tokens = Lexer(expression).tokenize()
        tree = Parser(tokens).parse()
        result = Executor(env).execute(tree)

        if isinstance(result, list):
            click.echo(format_array(result))
        elif isinstance(result, Relation):
            click.echo(format_relation(result))
        else:
            click.echo(result)
    except (LexError, ParseError, ExecutionError) as e:
        raise click.ClickException(str(e))


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
