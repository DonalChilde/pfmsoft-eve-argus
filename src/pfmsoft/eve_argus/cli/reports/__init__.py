"""Report commands for stored Argus data."""

import typer

from pfmsoft.eve_argus.cli.reports.corporation_blueprints import (
    app as corporation_blueprints_app,
)
from pfmsoft.eve_argus.cli.reports.corporation_jobs import app as corporation_jobs_app
from pfmsoft.eve_argus.cli.reports.history_summary import app as history_summary_app
from pfmsoft.eve_argus.cli.reports.hub_trades import app as hub_trades_app
from pfmsoft.eve_argus.cli.reports.price_summaries import app as price_summaries_app
from pfmsoft.eve_argus.cli.reports.scrapmetal import app as scrapmetal_app
from pfmsoft.eve_argus.cli.reports.station_trades import app as station_trades_app

app = typer.Typer(no_args_is_help=True, help="Generate reports from stored data.")
app.add_typer(corporation_jobs_app)
app.add_typer(corporation_blueprints_app)
app.add_typer(history_summary_app)
app.add_typer(price_summaries_app)
app.add_typer(scrapmetal_app)
app.add_typer(station_trades_app)
app.add_typer(hub_trades_app)
