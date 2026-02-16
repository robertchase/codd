"""CLI subcommand: repl."""

import click

from prototype.executor.environment import Environment
from prototype.repl.repl import run_repl


@click.command("repl")
@click.option("--load", "auto_load", is_flag=True, help="Auto-load sample data")
def repl_cmd(auto_load: bool) -> None:
    """Start the interactive REPL."""
    env = Environment()
    if auto_load:
        from prototype.data.sample import load_sample_data

        load_sample_data(env)
        click.echo("Sample data loaded: E, D, Phone, ContractorPay")

    run_repl(env)
