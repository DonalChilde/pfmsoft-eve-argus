"""Eve Argus command line interface."""

import typer

from pfmsoft.eve_argus.cli.util import app as util_app

app = typer.Typer(
    no_args_is_help=True,
    help="A command line interface for Eve Argus.",
)
app.add_typer(util_app, name="util")
