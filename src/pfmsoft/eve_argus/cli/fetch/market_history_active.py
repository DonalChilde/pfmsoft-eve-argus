"""Fetch active market types and their history sequentially by region."""

import asyncio
import logging
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from pfmsoft.eve_argus.cli.fetch._helpers import report_market_history_failure
from pfmsoft.eve_argus.cli.fetch._market_history_selection import (
    active_type_ids as _active_type_ids,
)
from pfmsoft.eve_argus.cli.helpers import get_eve_argus_settings_from_context
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.fetch_esi import market_history_bulk as bulk
from pfmsoft.eve_argus.fetch_esi.market_history import MarketHistoryUpdateResult
from pfmsoft.eve_argus.fetch_esi.update import UpdateStatus
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS
from pfmsoft.eve_argus.settings import EveArgusSettings
from pfmsoft.eve_argus.static import read as static_read
from pfmsoft.eve_argus.static.models import TypesDataset

logger = logging.getLogger(__name__)
app = typer.Typer(no_args_is_help=True)


@app.command(name="market-history-active")
def fetch_market_history_active(
    ctx: typer.Context,
    region_id: Annotated[
        list[int] | None,
        typer.Option(
            "--region-id", help="Region ID to update; repeat in processing order."
        ),
    ] = None,
    hubs: Annotated[
        bool,
        typer.Option("--hubs", help="Include all defined market hub regions."),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Suppress progress messages, but not errors."),
    ] = False,
) -> None:
    """Fetch published active types' history with a progress bar and limit per region.

    ESI market types can include unpublished type IDs, so active types marked
    unpublished in the static types dataset are excluded. Active types missing from
    the static dataset are still fetched, with a warning to update the database.
    """
    region_ids = list(region_id or ())
    if hubs:
        region_ids.extend(hub.region_id for hub in MARKET_HUBS)
    if not region_ids:
        raise typer.BadParameter("Provide at least one --region-id or use --hubs.")
    settings = get_eve_argus_settings_from_context(ctx)
    asyncio.run(
        _fetch_market_history_active(
            settings=settings,
            region_ids=list(dict.fromkeys(region_ids)),
            quiet=quiet,
        )
    )


async def _fetch_market_history_active(
    *, settings: EveArgusSettings, region_ids: list[int], quiet: bool
) -> None:
    """Validate regions, finish each regional run, and report failures at the end."""
    messenger = Console(stderr=True, quiet=quiet)
    errors = Console(stderr=True)
    failed = False
    async with EveArgusResources(settings) as resources:
        regions = static_read.map_regions(resources.argus_static_db_connection)
        unknown_regions = set(region_ids) - regions.keys()
        if unknown_regions:
            raise typer.BadParameter(f"Unknown region IDs: {sorted(unknown_regions)}")
        types = static_read.types(
            resources.argus_static_db_connection, only_published=False
        )
        unpublished_type_ids = {
            type_id for type_id, record in types.items() if not record.published
        }

        for region_id in region_ids:
            region_label = f"{regions[region_id].name} ({region_id})"
            messenger.print(
                f"Discovering active market types: {region_label}", markup=False
            )
            try:
                type_ids = await _active_type_ids(
                    resources.esi_link, resources.esi_schema, region_id=region_id
                )
            except Exception as error:
                logger.exception(
                    "Active market-type discovery failed for region %s", region_id
                )
                errors.print(
                    f"Failed active-type discovery: {region_label}: "
                    f"{type(error).__name__}: {error}",
                    markup=False,
                )
                failed = True
                continue

            if not type_ids:
                messenger.print(
                    f"No active market types for {region_label}; nothing to update.",
                    markup=False,
                )
                continue
            excluded = len(type_ids & unpublished_type_ids)
            type_ids -= unpublished_type_ids
            unknown_type_ids = type_ids - types.keys()
            if unknown_type_ids:
                errors.print(
                    f"Warning: {region_label} has {len(unknown_type_ids)} active "
                    "type IDs missing from the static types dataset: "
                    f"{sorted(unknown_type_ids)}. Consider updating the static "
                    "database.",
                    markup=False,
                )
            if not type_ids:
                messenger.print(
                    f"No published active market types for {region_label}; "
                    f"excluded {excluded} unpublished; nothing to update.",
                    markup=False,
                )
                continue
            messenger.print(
                f"Region: {region_label}; selected {len(type_ids)} active types "
                f"({len(unknown_type_ids)} unknown); excluded {excluded} "
                f"unpublished; batch size {bulk.MARKET_HISTORY_BATCH_SIZE}.",
                markup=False,
            )
            summary = await _fetch_region_history(
                resources=resources,
                region_id=region_id,
                region_label=region_label,
                type_ids=type_ids,
                types=types,
                errors=errors,
                quiet=quiet,
            )
            messenger.print(
                f"Market history for {region_label}: updated={summary.updated}, "
                f"skipped={summary.skipped}, failed={summary.failed}, "
                f"cancelled={summary.cancelled}, not_started={summary.not_started}.",
                markup=False,
            )
            if summary.aborted:
                errors.print(
                    f"Aborted: {region_label} reached its regional limit of "
                    f"{bulk.MARKET_HISTORY_FAILURE_LIMIT} failed updates. "
                    "Pending tasks were cancelled; committed updates were retained.",
                    markup=False,
                )
            failed = failed or bool(summary.failed)
    if failed:
        raise typer.Exit(code=1)


async def _fetch_region_history(
    *,
    resources: EveArgusResources,
    region_id: int,
    region_label: str,
    type_ids: set[int],
    types: TypesDataset,
    errors: Console,
    quiet: bool,
) -> bulk.MarketHistoryBulkResult:
    """Schedule one region's types in ascending order with isolated run state."""
    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}", markup=False),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TextColumn(
            "updated={task.fields[updated]} skipped={task.fields[skipped]} "
            "failed={task.fields[failed]}"
        ),
        TextColumn("{task.fields[last_type]}", markup=False),
        console=errors,
        disable=quiet,
        transient=True,
    ) as progress:
        task_id = progress.add_task(
            f"Market history: {region_label}",
            total=len(type_ids),
            updated=0,
            skipped=0,
            failed=0,
            last_type="Waiting for updates",
        )
        counts = dict.fromkeys(UpdateStatus, 0)

        def report(
            region_id: int, type_id: int, result: MarketHistoryUpdateResult
        ) -> None:
            counts[result.status] += 1
            progress.update(
                task_id,
                advance=1,
                updated=counts[UpdateStatus.UPDATED],
                skipped=counts[UpdateStatus.SKIPPED],
                failed=counts[UpdateStatus.FAILED],
                last_type=f"type {type_id}",
            )
            if result.status is UpdateStatus.FAILED:
                report_market_history_failure(
                    messenger=errors,
                    region_label=region_label,
                    type_id=type_id,
                    type_record=types.get(type_id),
                    failure_message=result.failure_message,
                )

        return await bulk.update_market_histories(
            resources.esi_link,
            resources.esi_schema,
            resources.market_history_db_connection,
            region_ids={region_id},
            type_ids=type_ids,
            on_result=report,
            batch_size=bulk.MARKET_HISTORY_BATCH_SIZE,
            failure_limit=bulk.MARKET_HISTORY_FAILURE_LIMIT,
        )
