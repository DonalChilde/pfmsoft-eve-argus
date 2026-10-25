"""Export commands for stored Argus datasets."""

import typer

from pfmsoft.eve_argus.cli.export.market_groups import app as market_groups_app
from pfmsoft.eve_argus.cli.export.types import app as types_app

app = typer.Typer(
    no_args_is_help=True,
    name="export",
    help="Export commands for stored Argus datasets.",
)
app.add_typer(market_groups_app)
app.add_typer(types_app)
