"""CLI subcommand: repl."""

import os
import pathlib
import sys

import click

from prototype.data.loader import load_csv
from prototype.executor.environment import Environment
from prototype.repl.repl import run_repl


@click.command("repl")
@click.argument("files", nargs=-1, type=click.Path())
@click.option(
    "--as",
    "aliases",
    multiple=True,
    help="Bind a file with an explicit name: --as name=path.csv",
)
@click.option("--load", "auto_load", is_flag=True, help="Auto-load sample data")
@click.option("--genkey", "genkey", is_flag=True, help="Generate synthetic key column")
def repl_cmd(
    files: tuple[str, ...],
    aliases: tuple[str, ...],
    auto_load: bool,
    genkey: bool,
) -> None:
    """Start the interactive REPL.

    Optionally load CSV files as relations before entering the REPL.
    Use - or --as name=- to read from stdin.
    """
    env = Environment()
    stdin_consumed = False

    if auto_load:
        from prototype.data.sample import load_sample_data

        load_sample_data(env)
        click.echo("Sample data loaded: E, D, Phone, ContractorPay")

    # Load aliased files (- means stdin)
    for alias in aliases:
        if "=" not in alias:
            raise click.ClickException(f"Invalid --as format: {alias!r} (expected name=path)")
        name, path = alias.split("=", 1)
        name = name.strip()
        path = path.strip()
        if path == "-":
            stdin_consumed = True
            _load_stdin(env, name, genkey=name if genkey else None)
        else:
            _load_file(env, path, name, genkey=name if genkey else None)

    # Load positional files (stem becomes name, - means stdin)
    for filepath in files:
        if filepath == "-":
            stdin_consumed = True
            _load_stdin(env, "stdin", genkey="stdin" if genkey else None)
        else:
            p = pathlib.Path(filepath)
            name = p.stem
            _load_file(env, filepath, name, genkey=name if genkey else None)

    # Auto-load stdin if piped and not already consumed
    if not stdin_consumed and not sys.stdin.isatty():
        _load_stdin(env, "stdin", genkey="stdin" if genkey else None)
        stdin_consumed = True

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
