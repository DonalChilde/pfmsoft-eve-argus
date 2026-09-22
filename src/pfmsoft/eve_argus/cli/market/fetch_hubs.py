"""Command to fetch market hub order data."""

from typing import Annotated

import typer
from rich.console import Console

from pfmsoft.eve_argus.cli.helpers import get_eve_argus_settings_from_context
from pfmsoft.eve_argus.data_loaders.esi_responses import EsiResponseLoader
from pfmsoft.eve_argus.data_transform.order_summaries import (
    OrderSummaryReport,
    calculate_summaries,
)
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.market.orders.db import query_helpers
from pfmsoft.eve_argus.models.esi import argus_response_models as ARM
from pfmsoft.eve_argus.models.esi import esi_response_models as ERM
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS

app = typer.Typer(no_args_is_help=True)


@app.command()
def fetch_hubs(
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            help="Suppress messages.",
            show_default=True,
        ),
    ] = False,
):
    """Fetch market hub order data."""
    if quiet:
        messenger = Console(stderr=True, quiet=True)
    else:
        messenger = Console(stderr=True)
    ...
    # use messenger to print messages to the console
    # Fetch market hub order data for each hub in MARKET_HUBS, write to database.
    # get orders from database
    # transform orders into summaries for hub system
    # write summaries to database
