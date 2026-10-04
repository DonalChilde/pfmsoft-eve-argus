"""Fetch market hub orders and summarize them in the dynamic database."""

import asyncio
import sqlite3
from math import ceil
from typing import Annotated

import typer
from pfmsoft.eve_link import EsiLink, EsiSchema
from rich.console import Console
from whenever import Instant

from pfmsoft.eve_argus.cli.helpers import get_eve_argus_settings_from_context
from pfmsoft.eve_argus.dynamic.access import DynamicDBReader, DynamicDBWriter
from pfmsoft.eve_argus.dynamic.db.order_summary import calculate_summaries
from pfmsoft.eve_argus.dynamic.update.market_orders import update_market_orders
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS, MarketHub
from pfmsoft.eve_argus.settings import EveArgusSettings

app = typer.Typer(no_args_is_help=True)


@app.command(name="fetch-hubs")
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
    """Fetch market hub order data into the dynamic database."""
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
        reader = DynamicDBReader()
        writer = DynamicDBWriter()
        for hub in MARKET_HUBS:
            try:
                await _fetch_hub(
                    hub=hub,
                    esi_link=resources.esi_link,
                    schema=resources.esi_schema,
                    connection=resources.argus_dynamic_db_connection,
                    reader=reader,
                    writer=writer,
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
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: sqlite3.Connection,
    reader: DynamicDBReader,
    writer: DynamicDBWriter,
    messenger: Console,
) -> None:
    """Fetch, store, and summarize one market hub in the dynamic database."""
    messenger.print(f"Checking market data for {hub.system_name}...")
    result = await update_market_orders(
        esi_link,
        schema,
        connection,
        region_id=hub.region_id,
    )
    if not result.update_successful:
        raise RuntimeError(result.failure_message or "Market orders update failed.")

    if result.update_not_required:
        messenger.print(f"Using cached market data for {hub.system_name}...")
        order_response = result.previous_state
        messenger.print("\tOrders already in database.")
    else:
        order_response = result.new_state
    if order_response is None:
        raise ValueError("No matching market orders response found after writing.")
    expiration = order_response.argus_expires_at or order_response.expires_at
    if expiration is None:
        messenger.print("\tDataset expiration is unavailable.")
    else:
        seconds_until_expiration = (
            Instant.parse_iso(expiration) - Instant.now()
        ).total("seconds")
        if seconds_until_expiration >= 0:
            messenger.print(
                f"\tDataset expires in {ceil(seconds_until_expiration)} seconds."
            )
        else:
            messenger.print(
                f"\tDataset expired {ceil(-seconds_until_expiration)} seconds ago."
            )
    region_orders = reader.read_market_orders(
        connection, response_metadata_id=order_response.response_metadata_id
    )
    if not result.update_not_required:
        order_count = sum(
            len(orders.buy_orders) + len(orders.sell_orders)
            for orders in region_orders.records.values()
        )
        messenger.print(f"\tFetched and stored {order_count} orders.")
    report = calculate_summaries(region_orders, system_id=hub.system_id)
    messenger.print(
        f"\tCalculated order summaries for {len(report.records.keys())} types."
    )
    writer.write_order_summaries(connection, order_summaries=report)
    messenger.print("\tWrote order summaries to database.")
