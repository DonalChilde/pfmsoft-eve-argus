"""Fetch market history for published market types across selected regions."""

import asyncio
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import (
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text

from pfmsoft.eve_argus.cli.fetch._helpers import report_market_history_failure
from pfmsoft.eve_argus.cli.helpers import get_eve_argus_settings_from_context
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.fetch_esi import market_history_bulk as bulk
from pfmsoft.eve_argus.fetch_esi.market_history import MarketHistoryUpdateResult
from pfmsoft.eve_argus.fetch_esi.update import UpdateStatus
from pfmsoft.eve_argus.helpers.market_groups import filter_type_ids_by_market_path
from pfmsoft.eve_argus.settings import EveArgusSettings
from pfmsoft.eve_argus.static import read as static_read
from pfmsoft.eve_argus.static.models import MarketGroupsDataset, TypesDataset

app = typer.Typer(no_args_is_help=True)


def _select_type_ids(
    *,
    market_groups: MarketGroupsDataset,
    types: TypesDataset,
    include: set[int],
    exclude: set[int],
) -> set[int]:
    """Validate filters/static paths and select published, market-listed types.

    Raises:
        ValueError: If datasets are missing, filters are unknown, or published
            type/group references are inconsistent.
    """
    if not market_groups or not types:
        raise ValueError("Static market groups and published types must be populated.")
    unknown = (include | exclude) - market_groups.keys()
    if unknown:
        raise ValueError(f"Unknown market group IDs: {sorted(unknown)}")

    published_ids = {key for key, record in types.items() if record.published}
    for type_id in published_ids:
        record = types[type_id]
        if record.type_id != type_id:
            raise ValueError(f"Static type key {type_id} disagrees with record ID.")
        if (
            record.market_group_id is not None
            and record.market_group_id not in market_groups
        ):
            raise ValueError(
                f"Missing market group {record.market_group_id} for type {type_id}."
            )
    for group_id, group in market_groups.items():
        if (
            group.market_group_id != group_id
            or not group.int_path
            or group.int_path[-1] != group_id
            or not set(group.int_path) <= market_groups.keys()
        ):
            raise ValueError(f"Invalid market path for group {group_id}.")
        for type_id in group.types:
            if type_id in published_ids and types[type_id].market_group_id != group_id:
                raise ValueError(
                    f"Market group {group_id} has an inconsistent reference to type {type_id}."
                )
    return (
        filter_type_ids_by_market_path(
            market_groups, include=include or None, exclude=exclude
        )
        & published_ids
    )


@app.command(name="market-history-bulk")
def fetch_market_history_bulk(
    ctx: typer.Context,
    region_id: Annotated[
        list[int],
        typer.Option(
            "--region-id", help="Region ID to update; repeat for multiple regions."
        ),
    ],
    include: Annotated[
        list[int] | None,
        typer.Option(
            "--include", help="Include a market-group subtree; repeat to combine."
        ),
    ] = None,
    exclude: Annotated[
        list[int] | None,
        typer.Option(
            "--exclude", help="Exclude a market-group subtree after includes."
        ),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Suppress progress messages, but not errors."),
    ] = False,
) -> None:
    """Fetch published market types in batches of 100; abort after 20 failures."""
    settings = get_eve_argus_settings_from_context(ctx)
    asyncio.run(
        _fetch_market_history_bulk(
            settings=settings,
            region_ids=set(region_id),
            include=set(include or ()),
            exclude=set(exclude or ()),
            quiet=quiet,
        )
    )


async def _fetch_market_history_bulk(
    *,
    settings: EveArgusSettings,
    region_ids: set[int],
    include: set[int],
    exclude: set[int],
    quiet: bool,
    show_progress: bool = False,
) -> None:
    """Validate static inputs, execute the bulk run, and report accurate totals."""
    messenger = Console(stderr=True, quiet=quiet)
    errors = Console(stderr=True)
    async with EveArgusResources(settings) as resources:
        connection = resources.argus_static_db_connection
        regions = static_read.map_regions(connection)
        unknown_regions = region_ids - regions.keys()
        if unknown_regions:
            raise typer.BadParameter(f"Unknown region IDs: {sorted(unknown_regions)}")
        types = static_read.types(connection, only_published=True)
        try:
            type_ids = _select_type_ids(
                market_groups=static_read.market_groups(connection),
                types=types,
                include=include,
                exclude=exclude,
            )
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error

        for region_id in sorted(region_ids):
            messenger.print(
                f"Region: {regions[region_id].name} ({region_id})", markup=False
            )
        total = len(region_ids) * len(type_ids)
        messenger.print(
            f"Selected {len(type_ids)} types across {len(region_ids)} regions: "
            f"{total} pairs; batch size {bulk.MARKET_HISTORY_BATCH_SIZE}."
        )
        if not type_ids:
            messenger.print("No market types selected; nothing to update.")
            return
        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TextColumn(
                "updated={task.fields[updated]} skipped={task.fields[skipped]} "
                "failed={task.fields[failed]}"
            ),
            TextColumn("{task.fields[last_pair]}", markup=False),
            console=errors,
            disable=quiet or not show_progress,
            transient=True,
        ) as progress:
            task_id = progress.add_task(
                "Market history",
                total=total,
                updated=0,
                skipped=0,
                failed=0,
                last_pair=Text("Waiting for updates"),
            )
            completed = 0
            counts = dict.fromkeys(UpdateStatus, 0)

            def report(
                region_id: int, type_id: int, result: MarketHistoryUpdateResult
            ) -> None:
                nonlocal completed
                completed += 1
                counts[result.status] += 1
                pair = f"{regions[region_id].name} ({region_id}), type {type_id}"
                if show_progress:
                    progress.update(
                        task_id,
                        advance=1,
                        updated=counts[UpdateStatus.UPDATED],
                        skipped=counts[UpdateStatus.SKIPPED],
                        failed=counts[UpdateStatus.FAILED],
                        last_pair=Text(pair),
                    )
                if result.status is UpdateStatus.FAILED:
                    report_market_history_failure(
                        messenger=errors,
                        region_label=f"{regions[region_id].name} ({region_id})",
                        type_id=type_id,
                        type_record=types.get(type_id),
                        failure_message=result.failure_message,
                    )
                if (
                    not show_progress
                    and completed % bulk.MARKET_HISTORY_BATCH_SIZE == 0
                ):
                    messenger.print(f"Completed {completed}/{total} pairs.")

            summary = await bulk.update_market_histories(
                resources.esi_link,
                resources.esi_schema,
                resources.market_history_db_connection,
                region_ids=region_ids,
                type_ids=type_ids,
                on_result=report,
                batch_size=bulk.MARKET_HISTORY_BATCH_SIZE,
                failure_limit=bulk.MARKET_HISTORY_FAILURE_LIMIT,
            )
        messenger.print(
            f"Market history: updated={summary.updated}, skipped={summary.skipped}, "
            f"failed={summary.failed}, cancelled={summary.cancelled}, "
            f"not_started={summary.not_started}."
        )
        if summary.aborted:
            errors.print(
                f"Aborted: reached the global limit of "
                f"{bulk.MARKET_HISTORY_FAILURE_LIMIT} failed updates. "
                "Pending tasks were cancelled; committed updates were retained."
            )
        if summary.failed:
            raise typer.Exit(code=1)


@app.command(name="market-history-bulk-progress")
def fetch_market_history_bulk_progress(
    ctx: typer.Context,
    region_id: Annotated[
        list[int],
        typer.Option(
            "--region-id", help="Region ID to update; repeat for multiple regions."
        ),
    ],
    include: Annotated[
        list[int] | None,
        typer.Option(
            "--include", help="Include a market-group subtree; repeat to combine."
        ),
    ] = None,
    exclude: Annotated[
        list[int] | None,
        typer.Option(
            "--exclude", help="Exclude a market-group subtree after includes."
        ),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Suppress progress messages, but not errors."),
    ] = False,
) -> None:
    """Compare bulk fetching with a live spinner, pair counts, and elapsed time."""
    settings = get_eve_argus_settings_from_context(ctx)
    asyncio.run(
        _fetch_market_history_bulk(
            settings=settings,
            region_ids=set(region_id),
            include=set(include or ()),
            exclude=set(exclude or ()),
            quiet=quiet,
            show_progress=True,
        )
    )
