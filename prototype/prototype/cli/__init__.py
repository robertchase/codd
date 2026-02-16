"""CLI entry point for the prototype."""

import click

from prototype.cli.eval_cmd import eval_cmd
from prototype.cli.repl_cmd import repl_cmd


@click.group()
def main() -> None:
    """Codd relational algebra prototype."""


main.add_command(repl_cmd)
main.add_command(eval_cmd)
