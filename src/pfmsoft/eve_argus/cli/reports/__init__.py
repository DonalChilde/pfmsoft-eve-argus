"""Report commands for stored Argus data."""

import typer

from pfmsoft.eve_argus.cli.reports.corporation_blueprints import (
    app as corporation_blueprints_app,
)
from pfmsoft.eve_argus.cli.reports.corporation_jobs import app as corporation_jobs_app

app = typer.Typer(no_args_is_help=True, help="Generate reports from stored data.")
app.add_typer(corporation_jobs_app)
app.add_typer(corporation_blueprints_app)
