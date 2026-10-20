"""Eve Argus command line interface."""

import typer

from pfmsoft.eve_argus.cli.export import app as export_app
from pfmsoft.eve_argus.cli.fetch import app as fetch_app
from pfmsoft.eve_argus.cli.market import app as market_app
from pfmsoft.eve_argus.cli.reports import app as reports_app
from pfmsoft.eve_argus.cli.static import app as static_app
from pfmsoft.eve_argus.cli.util import app as util_app

app = typer.Typer(
    no_args_is_help=True,
    help="A command line interface for Eve Argus.",
)
app.add_typer(util_app, name="util")
app.add_typer(market_app, name="market")
app.add_typer(static_app, name="static")
app.add_typer(fetch_app, name="fetch")
app.add_typer(reports_app, name="reports")
app.add_typer(export_app, name="export")
