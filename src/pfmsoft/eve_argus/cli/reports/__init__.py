"""Report commands for stored Argus data."""

import typer

from pfmsoft.eve_argus.cli.reports.corporation_jobs import app as corporation_jobs_app

app = typer.Typer(no_args_is_help=True, help="Generate reports from stored data.")
app.add_typer(corporation_jobs_app)
