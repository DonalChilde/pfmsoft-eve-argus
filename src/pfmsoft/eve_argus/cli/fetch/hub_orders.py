"""Fetch market hub orders and report update results."""

import asyncio
import sqlite3
from typing import Annotated

import typer
from pfmsoft.eve_link import EsiLink, EsiSchema
from rich.console import Console

from pfmsoft.eve_argus.cli.fetch._helpers import report_update_result
from pfmsoft.eve_argus.cli.helpers import get_eve_argus_settings_from_context
from pfmsoft.eve_argus.dynamic import read, write
from pfmsoft.eve_argus.dynamic.order_summary import calculate_summaries
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.fetch_esi import update_market_orders
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS, MarketHub
from pfmsoft.eve_argus.settings import EveArgusSettings

app = typer.Typer(no_args_is_help=True)


@app.command(name="hub-orders")
def fetch_hub_orders(
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
    """Fetch market hub order data into the dynamic database."""
    settings = get_eve_argus_settings_from_context(ctx)
    if quiet:
        messenger = Console(stderr=True, quiet=True)
    else:
        messenger = Console(stderr=True)

    asyncio.run(_fetch_hubs(settings=settings, messenger=messenger))


async def _fetch_hubs(*, settings: EveArgusSettings, messenger: Console) -> None:
    """Fetch market orders for each configured hub."""
    async with EveArgusResources(settings) as resources:
        for hub in MARKET_HUBS:
            await _fetch_hub(
                hub=hub,
                esi_link=resources.esi_link,
                schema=resources.esi_schema,
                connection=resources.argus_dynamic_db_connection,
                messenger=messenger,
            )


async def _fetch_hub(
    *,
    hub: MarketHub,
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: sqlite3.Connection,
    messenger: Console,
) -> None:
    """Fetch market orders for one hub and report the update result."""
    messenger.print(f"Checking market data for {hub.system_name}...")
    result = await update_market_orders(
        esi_link,
        schema,
        connection,
        region_id=hub.region_id,
    )
    order_response = report_update_result(
        result,
        messenger=messenger,
        dataset_name=f"market orders for {hub.system_name}",
    )
    if result.new_state is not None:
        region_orders = read.market_orders(
            connection, response_metadata_id=order_response.response_metadata_id
        )
        order_count = sum(
            len(orders.buy_orders) + len(orders.sell_orders)
            for orders in region_orders.records.values()
        )
        messenger.print(f"\tRead {order_count} orders from the database.")
        report = calculate_summaries(region_orders, system_id=hub.system_id)
        messenger.print(
            f"\tCalculated order summaries for {len(report.records)} types."
        )
        write.order_summaries(connection, order_summaries=report)
        messenger.print("\tUpdated order summaries in the database.")
