"""Fetch market orders for explicit regions and configured hub regions."""

import asyncio
from typing import Annotated

import typer
from rich.console import Console

from pfmsoft.eve_argus.cli.fetch._helpers import report_update_result
from pfmsoft.eve_argus.cli.helpers import get_eve_argus_settings_from_context
from pfmsoft.eve_argus.dynamic import read
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.fetch_esi import update_market_orders
from pfmsoft.eve_argus.fetch_esi.update import UpdateStatus
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS
from pfmsoft.eve_argus.settings import EveArgusSettings

app = typer.Typer(no_args_is_help=True)


@app.command(name="market-orders")
def fetch_market_orders(
    ctx: typer.Context,
    region_id: Annotated[
        list[int] | None,
        typer.Option(
            "--region-id",
            help="Region ID; repeat in processing order.",
        ),
    ] = None,
    hubs: Annotated[
        bool, typer.Option("--hubs", help="Append all defined market hub regions.")
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            help="Suppress progress messages, but not errors.",
            show_default=True,
        ),
    ] = False,
) -> None:
    """Store regional orders without precomputing price summaries.

    Explicit regions are processed first, then hub regions. Duplicate regions
    are fetched only once. A failed update stops further processing.
    """
    region_ids = list(region_id or ())
    if hubs:
        region_ids.extend(hub.region_id for hub in MARKET_HUBS)
    if not region_ids:
        raise typer.BadParameter("Provide at least one --region-id or use --hubs.")
    settings = get_eve_argus_settings_from_context(ctx)
    messenger = Console(stderr=True, quiet=quiet)
    errors = Console(stderr=True)
    asyncio.run(
        _fetch_region_orders(
            settings=settings,
            region_ids=list(dict.fromkeys(region_ids)),
            messenger=messenger,
            errors=errors,
        )
    )


async def _fetch_region_orders(
    *,
    settings: EveArgusSettings,
    region_ids: list[int],
    messenger: Console,
    errors: Console,
) -> None:
    """Fetch selected regions with shared resources and report update results."""
    async with EveArgusResources(settings) as resources:
        for region_id in region_ids:
            messenger.print(f"Checking market data for region {region_id}...")
            result = await update_market_orders(
                resources.esi_link,
                resources.esi_schema,
                resources.argus_dynamic_db_connection,
                region_id=region_id,
            )
            response = (
                result.previous_state
                if result.status is UpdateStatus.SKIPPED
                else result.new_state
            )
            response = report_update_result(
                result,
                messenger=(
                    errors
                    if result.status is UpdateStatus.FAILED or response is None
                    else messenger
                ),
                dataset_name=f"market orders for region {region_id}",
            )
            order_count = read.market_order_count(
                resources.argus_dynamic_db_connection,
                response_metadata_id=response.response_metadata_id,
            )
            messenger.print(f"\tStored orders: {order_count:,}")
