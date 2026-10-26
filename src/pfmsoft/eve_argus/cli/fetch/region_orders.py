"""Fetch market orders for explicit regions and configured hub regions."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from pfmsoft.eve_argus.cli.fetch._helpers import report_update_result
from pfmsoft.eve_argus.cli.fetch._selection_file import (
    load_selection_file,
    validate_region_ids,
)
from pfmsoft.eve_argus.cli.helpers import get_eve_argus_settings_from_context
from pfmsoft.eve_argus.dynamic import read
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.fetch_esi import update_market_orders
from pfmsoft.eve_argus.fetch_esi.update import UpdateStatus
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS
from pfmsoft.eve_argus.settings import EveArgusSettings
from pfmsoft.eve_argus.static import read as static_read

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
    from_file: Annotated[
        Path | None,
        typer.Option(
            "--from",
            help="JSON file with a 'region_ids' list; fetched after --region-id.",
            dir_okay=False,
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

    Explicit regions are processed first, then regions from the --from file,
    then hub regions. File regions must exist in the static database. Duplicate
    regions are fetched only once. A failed update stops further processing.
    """
    region_ids = list(region_id or ())
    file_region_ids: tuple[int, ...] = ()
    if from_file is not None:
        try:
            file_region_ids = load_selection_file(
                from_file, require_type_ids=False
            ).region_ids
        except ValueError as error:
            raise typer.BadParameter(str(error), param_hint="--from") from error
        region_ids.extend(file_region_ids)
    if hubs:
        region_ids.extend(hub.region_id for hub in MARKET_HUBS)
    if not region_ids:
        raise typer.BadParameter(
            "Provide at least one --region-id, use --from, or use --hubs."
        )
    settings = get_eve_argus_settings_from_context(ctx)
    messenger = Console(stderr=True, quiet=quiet)
    errors = Console(stderr=True)
    asyncio.run(
        _fetch_region_orders(
            settings=settings,
            region_ids=list(dict.fromkeys(region_ids)),
            file_region_ids=file_region_ids,
            messenger=messenger,
            errors=errors,
        )
    )


async def _fetch_region_orders(
    *,
    settings: EveArgusSettings,
    region_ids: list[int],
    file_region_ids: tuple[int, ...],
    messenger: Console,
    errors: Console,
) -> None:
    """Fetch selected regions with shared resources and report update results.

    Raises:
        typer.BadParameter: If a file region is missing from the static database.
    """
    async with EveArgusResources(settings) as resources:
        if file_region_ids:
            regions = static_read.map_regions(resources.argus_static_db_connection)
            try:
                validate_region_ids(file_region_ids, known_region_ids=regions.keys())
            except ValueError as error:
                raise typer.BadParameter(str(error), param_hint="--from") from error
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
