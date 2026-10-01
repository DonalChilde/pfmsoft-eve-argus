"""Fetch market hub orders and summarize them in the dynamic database."""

import asyncio
import sqlite3
from typing import Annotated

import typer
from rich.console import Console
from whenever import Instant

from pfmsoft.eve_argus.cli.helpers import get_eve_argus_settings_from_context
from pfmsoft.eve_argus.data_loaders.esi_responses import EsiResponseLoader
from pfmsoft.eve_argus.dynamic.access import DynamicDBReader, DynamicDBWriter
from pfmsoft.eve_argus.dynamic.db.order_summary import calculate_summaries
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.models.esi import esi_response_models as ERM
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS, MarketHub
from pfmsoft.eve_argus.settings import EveArgusSettings

app = typer.Typer(no_args_is_help=True)


@app.command(name="fetch_hubs_2")
def fetch_hubs_2(
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

    failed_hubs = asyncio.run(_fetch_hubs_2(settings=settings, messenger=messenger))
    if failed_hubs:
        raise typer.Exit(code=1)


async def _fetch_hubs_2(*, settings: EveArgusSettings, messenger: Console) -> list[str]:
    """Fetch and summarize orders for each configured market hub."""
    failed_hubs: list[str] = []
    async with EveArgusResources(settings) as resources:
        loader = EsiResponseLoader(
            esi_link=resources.esi_link, schema=resources.esi_schema
        )
        reader = DynamicDBReader()
        writer = DynamicDBWriter()
        for hub in MARKET_HUBS:
            try:
                await _fetch_hub_2(
                    hub=hub,
                    loader=loader,
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


async def _fetch_hub_2(
    *,
    hub: MarketHub,
    loader: EsiResponseLoader,
    connection: sqlite3.Connection,
    reader: DynamicDBReader,
    writer: DynamicDBWriter,
    messenger: Console,
) -> None:
    """Fetch, store, and summarize one market hub in the dynamic database."""
    stored_responses = reader.read_market_orders_responses(
        connection, region_id=hub.region_id
    )
    latest = stored_responses[-1] if stored_responses else None
    expires_at = (latest.argus_expires_at or latest.expires_at) if latest else None
    if (
        latest is not None
        and expires_at
        and Instant.parse_iso(expires_at) > Instant.now()
    ):
        messenger.print(f"Using cached market data for {hub.system_name}...")
        order_response = latest
        messenger.print("\tOrders already in database.")
    else:
        messenger.print(f"Fetching market data for {hub.system_name}...")
        response: ERM.GetMarketsRegionIdOrdersResponse = (
            await loader.region_market_orders(region_id=hub.region_id)
        )
        messenger.print(f"\tFetched {len(response.response_data.orders)} orders.")
        order_response = next(
            (
                stored
                for stored in stored_responses
                if stored.received_at == response.response_data.received_at
            ),
            None,
        )
        if (
            order_response is not None
            and expires_at
            and Instant.parse_iso(expires_at) <= Instant.now()
        ):
            raise ValueError(
                "ESI returned an expired order set without a new received_at."
            )
        if order_response is None:
            writer.write_market_orders(connection, market_orders=response.response_data)
            messenger.print("\tWrote orders to database.")
            order_response = next(
                (
                    stored
                    for stored in reader.read_market_orders_responses(
                        connection, region_id=hub.region_id
                    )
                    if stored.received_at == response.response_data.received_at
                ),
                None,
            )
        else:
            messenger.print("\tOrders already in database.")
    if order_response is None:
        raise ValueError("No matching market orders response found after writing.")
    region_orders = reader.read_market_orders(
        connection, response_metadata_id=order_response.response_metadata_id
    )
    report = calculate_summaries(region_orders, system_id=hub.system_id)
    messenger.print(
        f"\tCalculated order summaries for {len(report.records.keys())} types."
    )
    writer.write_order_summaries(connection, order_summaries=report)
    messenger.print("\tWrote order summaries to database.")
