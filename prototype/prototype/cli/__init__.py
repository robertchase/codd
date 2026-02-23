"""CLI entry point for the prototype."""

import click

from prototype.cli.eval_cmd import eval_cmd
from prototype.cli.ops_cmd import ops_cmd
from prototype.cli.repl_cmd import repl_cmd


@click.group()
def main() -> None:
    """Codd relational algebra prototype."""


main.add_command(repl_cmd)
main.add_command(eval_cmd)
main.add_command(ops_cmd)
