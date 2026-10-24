"""Fetch individual region market-order data."""

import asyncio
from typing import Annotated

import typer
from rich.console import Console

from pfmsoft.eve_argus.cli.fetch._helpers import report_update_result
from pfmsoft.eve_argus.cli.helpers import get_eve_argus_settings_from_context
from pfmsoft.eve_argus.dynamic import read, write
from pfmsoft.eve_argus.dynamic.order_summary import calculate_dataset_summaries
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.fetch_esi import update_market_orders
from pfmsoft.eve_argus.fetch_esi.update import UpdateStatus
from pfmsoft.eve_argus.settings import EveArgusSettings

app = typer.Typer(no_args_is_help=True)


@app.command(name="market-orders")
def fetch_market_orders(
    ctx: typer.Context,
    region_id: Annotated[
        int,
        typer.Option(
            "--region-id",
            help="The ID of the region to fetch orders for.",
            show_default=True,
        ),
    ],
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            help="Suppress messages.",
            show_default=True,
        ),
    ] = False,
) -> None:
    """Fetch region order data into the dynamic database."""
    settings = get_eve_argus_settings_from_context(ctx)
    messenger = Console(stderr=True, quiet=quiet)
    asyncio.run(
        _fetch_region_orders(
            settings=settings, region_id=region_id, messenger=messenger
        )
    )


async def _fetch_region_orders(
    *, settings: EveArgusSettings, region_id: int, messenger: Console
) -> None:
    """Fetch market orders for one region and report the result."""
    messenger.print(f"Checking market data for region {region_id}...")
    async with EveArgusResources(settings) as resources:
        result = await update_market_orders(
            resources.esi_link,
            resources.esi_schema,
            resources.argus_dynamic_db_connection,
            region_id=region_id,
        )
        response = report_update_result(
            result, messenger=messenger, dataset_name="market orders"
        )
        if result.status is not UpdateStatus.SKIPPED:
            orders = read.market_orders(
                resources.argus_dynamic_db_connection,
                response_metadata_id=response.response_metadata_id,
            )
            order_count = sum(
                len(group.buy_orders) + len(group.sell_orders)
                for group in orders.records.values()
            )
            messenger.print(f"\tRead {order_count} orders from the database.")
            summaries = calculate_dataset_summaries(orders)
            messenger.print(
                f"\tCalculated order summaries for {len(summaries.records)} types."
            )
            write.order_summaries(
                resources.argus_dynamic_db_connection, order_summaries=summaries
            )
            messenger.print("\tUpdated order summaries in the database.")
