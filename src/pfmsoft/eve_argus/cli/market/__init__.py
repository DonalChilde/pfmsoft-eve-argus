"""Market commands."""

import typer

from pfmsoft.eve_argus.cli.market.fetch_hubs import app as fetch_hubs_app
from pfmsoft.eve_argus.cli.market.fetch_hubs_2 import app as fetch_hubs_2_app

app = typer.Typer(no_args_is_help=True, name="market", help="Market related commands")

app.add_typer(fetch_hubs_app)
app.add_typer(fetch_hubs_2_app)
