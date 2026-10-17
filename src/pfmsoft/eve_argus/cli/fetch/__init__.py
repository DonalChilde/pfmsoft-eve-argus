"""Commands for fetching data."""

import typer

from pfmsoft.eve_argus.cli.fetch.hub_orders import app as fetch_hubs_app

app = typer.Typer(no_args_is_help=True, help="Commands for fetching data.")
app.add_typer(fetch_hubs_app)
