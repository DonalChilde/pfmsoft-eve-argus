"""Command to fetch market hub order data."""

import asyncio
import sqlite3
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
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS, MarketHub
from pfmsoft.eve_argus.settings import EveArgusSettings

app = typer.Typer(no_args_is_help=True)


@app.command()
def fetch_hubs(
    ctx: typer.Context,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            help="Suppress messages.",
            show_default=True,
        ),
    ] = False,
) -> None:
    """Fetch market hub order data."""
    settings = get_eve_argus_settings_from_context(ctx)
    if quiet:
        messenger = Console(stderr=True, quiet=True)
    else:
        messenger = Console(stderr=True)

    failed_hubs = asyncio.run(_fetch_hubs(settings=settings, messenger=messenger))
    if failed_hubs:
        raise typer.Exit(code=1)


async def _fetch_hubs(*, settings: EveArgusSettings, messenger: Console) -> list[str]:
    """Fetch and summarize orders for each configured market hub."""
    failed_hubs: list[str] = []
    async with EveArgusResources(settings) as resources:
        loader = EsiResponseLoader(
            esi_link=resources.esi_link, schema=resources.esi_schema
        )
        for hub in MARKET_HUBS:
            try:
                await _fetch_hub(
                    hub=hub,
                    loader=loader,
                    connection=resources.order_db_connection,
                    messenger=messenger,
                )
            except Exception as error:
                failed_hubs.append(hub.region_name)
                messenger.print(
                    f"Failed to fetch {hub.system_name} market data: {error}"
                )
    return failed_hubs


async def _fetch_hub(
    *,
    hub: MarketHub,
    loader: EsiResponseLoader,
    connection: sqlite3.Connection,
    messenger: Console,
) -> None:
    """Fetch, store, and summarize one market hub."""
    messenger.print(f"Fetching market data for {hub.system_name}...")
    response: ERM.GetMarketsRegionIdOrdersResponse = await loader.region_market_orders(
        region_id=hub.region_id
    )
    messenger.print(f"\tFetched {len(response.response_data.orders)} orders.")
    query_helpers.write_market_orders(connection, response.response_data)
    messenger.print(f"\tWrote orders to database.")

    order_response = query_helpers.get_order_response(connection, hub.region_id)
    region_orders: ARM.RegionMarketOrders = query_helpers.get_region_market_orders(
        connection, order_response
    )
    report: OrderSummaryReport = calculate_summaries(
        region_orders, system_id=hub.system_id
    )
    messenger.print(
        f"\tCalculated order summaries for {len(report.summaries.keys())} types."
    )
    query_helpers.write_order_summaries(connection, report.iter_summaries())
    messenger.print(f"\tWrote order summaries to database.")
