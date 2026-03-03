"""CLI entry point for codd."""

import click

from codd.cli.eval_cmd import eval_cmd
from codd.cli.ops_cmd import ops_cmd
from codd.cli.repl_cmd import repl_cmd


@click.group()
def main() -> None:
    """Codd relational algebra."""


main.add_command(repl_cmd)
main.add_command(eval_cmd)
main.add_command(ops_cmd)
