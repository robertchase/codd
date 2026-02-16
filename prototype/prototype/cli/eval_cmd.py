"""CLI subcommand: eval."""

import click

from prototype.data.sample import load_sample_data
from prototype.executor.environment import Environment
from prototype.executor.executor import Executor, ExecutionError
from prototype.lexer.lexer import Lexer, LexError
from prototype.model.relation import Relation
from prototype.parser.parser import Parser, ParseError
from prototype.repl.formatter import format_array, format_relation


@click.command("eval")
@click.argument("expression")
@click.option("--load", "auto_load", is_flag=True, default=True, help="Auto-load sample data")
def eval_cmd(expression: str, auto_load: bool) -> None:
    """Evaluate a single expression and print the result."""
    env = Environment()
    if auto_load:
        load_sample_data(env)

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
