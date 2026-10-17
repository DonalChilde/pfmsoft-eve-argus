"""Commands for working with static data."""

import typer

from pfmsoft.eve_argus.cli.static.import_db import app as import_db_app

app = typer.Typer(
    no_args_is_help=True,
    help="Commands for working with static data sets.",
)
app.add_typer(import_db_app)
