"""Fetch market history with shared selection and regional execution."""

import asyncio
import logging
from dataclasses import dataclass
from enum import StrEnum
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

from pfmsoft.eve_argus.cli.fetch._helpers import (
    report_market_history_failure,
    report_update_result,
)
from pfmsoft.eve_argus.cli.fetch._market_history_selection import (
    active_type_ids,
    select_market_type_ids,
)
from pfmsoft.eve_argus.cli.helpers import get_eve_argus_settings_from_context
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.fetch_esi import market_history_bulk as bulk
from pfmsoft.eve_argus.fetch_esi.market_history import MarketHistoryUpdateResult
from pfmsoft.eve_argus.fetch_esi.update import UpdateStatus
from pfmsoft.eve_argus.helpers.market_groups import filter_type_ids_by_market_path
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS
from pfmsoft.eve_argus.settings import EveArgusSettings
from pfmsoft.eve_argus.static import read as static_read
from pfmsoft.eve_argus.static.helpers import types_in_blueprint
from pfmsoft.eve_argus.static.models import TypesDataset

logger = logging.getLogger(__name__)
app = typer.Typer(no_args_is_help=True)


class ProgressStyle(StrEnum):
    """Available terminal reporting styles."""

    AUTO = "auto"
    LIVE = "live"
    PLAIN = "plain"


class SelectionMode(StrEnum):
    """Mutually exclusive sources of candidate types."""

    EXPLICIT = "explicit"
    ACTIVE = "active"
    MARKET = "market"
    INDUSTRY = "industry"


@dataclass(slots=True, kw_only=True, frozen=True)
class HistoryFetchOptions:
    """Validated command options shared by each regional run."""

    region_ids: list[int]
    type_ids: set[int]
    selection: SelectionMode
    include: set[int]
    exclude: set[int]
    worker_count: int
    failure_limit: int
    progress: ProgressStyle
    quiet: bool

    @property
    def single_pair(self) -> bool:
        """Whether explicit selection requests exactly one region/type pair."""
        return (
            self.selection is SelectionMode.EXPLICIT
            and len(self.region_ids) == 1
            and len(self.type_ids) == 1
        )


@app.command(name="market-history")
def fetch_market_history(
    ctx: typer.Context,
    region_id: Annotated[
        list[int] | None,
        typer.Option("--region-id", help="Region ID; repeat in processing order."),
    ] = None,
    type_id: Annotated[
        list[int] | None,
        typer.Option("--type-id", help="Explicit item type ID; repeat to combine."),
    ] = None,
    hubs: Annotated[
        bool, typer.Option("--hubs", help="Append all defined market hub regions.")
    ] = False,
    active: Annotated[
        bool,
        typer.Option("--active", help="Discover published market-listed active types."),
    ] = False,
    market_types: Annotated[
        bool,
        typer.Option("--market-types", help="Select published market-listed types."),
    ] = False,
    industry_types: Annotated[
        bool,
        typer.Option(
            "--industry-types",
            help="Select published market-listed blueprint, material, and product types.",
        ),
    ] = False,
    include: Annotated[
        list[int] | None,
        typer.Option(
            "--include", help="Include a market-group subtree; repeat to combine."
        ),
    ] = None,
    exclude: Annotated[
        list[int] | None,
        typer.Option(
            "--exclude", help="Exclude a market-group subtree; exclusions win."
        ),
    ] = None,
    worker_count: Annotated[
        int | None,
        typer.Option(
            "--workers",
            min=1,
            help=f"Concurrent update workers (default: MARKET_HISTORY_WORKER_COUNT = {bulk.MARKET_HISTORY_WORKER_COUNT}).",
            show_default=False,
        ),
    ] = None,
    failure_limit: Annotated[
        int | None,
        typer.Option(
            "--failure-limit",
            min=1,
            help=f"Failed updates before aborting a region (default: MARKET_HISTORY_FAILURE_LIMIT = {bulk.MARKET_HISTORY_FAILURE_LIMIT}).",
            show_default=False,
        ),
    ] = None,
    progress: Annotated[
        ProgressStyle,
        typer.Option(
            "--progress", help="Auto uses live progress on interactive terminals."
        ),
    ] = ProgressStyle.AUTO,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Suppress progress messages, but not errors."),
    ] = False,
) -> None:
    """Fetch history using exactly one type-selection mode, region by region.

    Includes/excludes apply to active, market, and industry selections,
    not explicit type IDs. Each region has an independent failure budget.
    """
    region_ids = list(region_id or ())
    if hubs:
        region_ids.extend(hub.region_id for hub in MARKET_HUBS)
    if not region_ids:
        raise typer.BadParameter("Provide at least one --region-id or use --hubs.")
    selections = [
        mode
        for mode, enabled in (
            (SelectionMode.EXPLICIT, bool(type_id)),
            (SelectionMode.ACTIVE, active),
            (SelectionMode.MARKET, market_types),
            (SelectionMode.INDUSTRY, industry_types),
        )
        if enabled
    ]
    if len(selections) != 1:
        raise typer.BadParameter(
            "Choose exactly one of --type-id, --active, --market-types, "
            "or --industry-types."
        )
    selection = selections[0]
    if selection is SelectionMode.EXPLICIT and (include or exclude):
        raise typer.BadParameter(
            "--include and --exclude cannot be used with --type-id."
        )
    options = HistoryFetchOptions(
        region_ids=list(dict.fromkeys(region_ids)),
        type_ids=set(type_id or ()),
        selection=selection,
        include=set(include or ()),
        exclude=set(exclude or ()),
        worker_count=(
            bulk.MARKET_HISTORY_WORKER_COUNT if worker_count is None else worker_count
        ),
        failure_limit=(
            bulk.MARKET_HISTORY_FAILURE_LIMIT
            if failure_limit is None
            else failure_limit
        ),
        progress=progress,
        quiet=quiet,
    )
    settings = get_eve_argus_settings_from_context(ctx)
    asyncio.run(_fetch_market_history(settings=settings, options=options))


async def _fetch_market_history(
    *, settings: EveArgusSettings, options: HistoryFetchOptions
) -> None:
    """Validate selection, finish each regional run, then report overall totals."""
    messenger = Console(stderr=True, quiet=options.quiet)
    errors = Console(stderr=True)
    totals = bulk.MarketHistoryBulkResult(total=0)
    discovery_failed = 0
    async with EveArgusResources(settings) as resources:
        connection = resources.argus_static_db_connection
        regions = static_read.map_regions(connection)
        unknown_regions = set(options.region_ids) - regions.keys()
        if unknown_regions and not options.single_pair:
            raise typer.BadParameter(f"Unknown region IDs: {sorted(unknown_regions)}")
        types = static_read.types(connection, only_published=False)
        selected_ids = options.type_ids
        excluded_ids: set[int] = set()
        if (
            options.selection is SelectionMode.MARKET
            or options.include
            or options.exclude
        ):
            groups = static_read.market_groups(connection)
            try:
                selected_ids = select_market_type_ids(
                    market_groups=groups,
                    types=types,
                    include=options.include,
                    exclude=options.exclude,
                )
            except ValueError as error:
                raise typer.BadParameter(str(error)) from error
            if options.exclude:
                excluded_ids = filter_type_ids_by_market_path(
                    groups, include=options.exclude
                )
        unpublished_ids = {
            type_id for type_id, record in types.items() if not record.published
        }
        market_ids = {
            type_id
            for type_id, record in types.items()
            if record.market_group_id is not None
        }
        industry_ids: set[int] = set()
        if options.selection is SelectionMode.INDUSTRY:
            blueprints = static_read.blueprints(connection)
            if not blueprints:
                raise typer.BadParameter("Static blueprints dataset must be populated.")
            for blueprint in blueprints.values():
                industry_ids.update(types_in_blueprint(blueprint))

        for region_id in options.region_ids:
            region = regions.get(region_id)
            label = f"{region.name if region is not None else 'Unknown region'} ({region_id})"
            type_ids = selected_ids
            if options.selection is SelectionMode.ACTIVE:
                messenger.print(
                    f"Discovering active market types: {label}", markup=False
                )
                try:
                    type_ids = await active_type_ids(
                        resources.esi_link, resources.esi_schema, region_id=region_id
                    )
                except Exception as error:
                    logger.exception(
                        "Active market-type discovery failed for region %s", region_id
                    )
                    errors.print(
                        f"Failed active-type discovery: {label}: "
                        f"{type(error).__name__}: {error}",
                        markup=False,
                    )
                    discovery_failed += 1
                    continue
            if options.selection in (SelectionMode.ACTIVE, SelectionMode.INDUSTRY):
                source = (
                    "active"
                    if options.selection is SelectionMode.ACTIVE
                    else "industry"
                )
                if options.selection is SelectionMode.INDUSTRY:
                    type_ids = industry_ids
                unpublished_count = len(type_ids & unpublished_ids)
                type_ids = type_ids - unpublished_ids
                unknown_ids = type_ids - types.keys()
                if unknown_ids:
                    errors.print(
                        f"Warning: {label} has {len(unknown_ids)} {source} type IDs "
                        f"missing from the static types dataset: {sorted(unknown_ids)}. "
                        "These IDs are excluded because market membership is unknown. "
                        "Consider updating the static database.",
                        markup=False,
                    )
                nonmarket_count = len(type_ids - market_ids)
                type_ids &= market_ids
                if options.include:
                    type_ids &= selected_ids
                type_ids = type_ids - excluded_ids
                messenger.print(
                    f"{label}: excluded {unpublished_count} unpublished {source} types; "
                    f"excluded {nonmarket_count} nonmarket or unknown types.",
                    markup=False,
                )
            messenger.print(
                f"Region: {label}; selected {len(type_ids)} types; "
                f"workers {options.worker_count}; failure limit {options.failure_limit}.",
                markup=False,
            )
            summary = await _fetch_region_history(
                resources=resources,
                options=options,
                region_id=region_id,
                region_label=label,
                type_ids=type_ids,
                types=types,
                messenger=messenger,
                errors=errors,
            )
            messenger.print(
                f"Market history for {label}: {_summary_text(summary)}",
                markup=False,
            )
            if summary.aborted:
                errors.print(
                    f"Aborted: {label} reached its regional limit of "
                    f"{options.failure_limit} failed updates. Pending tasks were "
                    "cancelled; committed updates were retained.",
                    markup=False,
                )
            totals.total += summary.total
            totals.updated += summary.updated
            totals.skipped += summary.skipped
            totals.failed += summary.failed
            totals.cancelled += summary.cancelled
    messenger.print(
        f"Market history total: {_summary_text(totals)} "
        f"discovery_failed={discovery_failed}."
    )
    if totals.failed or discovery_failed:
        raise typer.Exit(code=1)


def _summary_text(summary: bulk.MarketHistoryBulkResult) -> str:
    """Format reconciled totals without counting cancellation as completion."""
    return (
        f"updated={summary.updated}, skipped={summary.skipped}, failed={summary.failed}, "
        f"cancelled={summary.cancelled}, not_started={summary.not_started}."
    )


async def _fetch_region_history(
    *,
    resources: EveArgusResources,
    options: HistoryFetchOptions,
    region_id: int,
    region_label: str,
    type_ids: set[int],
    types: TypesDataset,
    messenger: Console,
    errors: Console,
) -> bulk.MarketHistoryBulkResult:
    """Execute one region with independent limits, counters, and progress cleanup."""
    if not type_ids:
        messenger.print("No market types selected; nothing to update.")
        return bulk.MarketHistoryBulkResult(total=0)
    live = options.progress is ProgressStyle.LIVE or (
        options.progress is ProgressStyle.AUTO and errors.is_terminal
    )
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
        disable=options.quiet or not live,
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
        completed = 0

        def report(
            region_id: int, type_id: int, result: MarketHistoryUpdateResult
        ) -> None:
            nonlocal completed
            completed += 1
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
            elif options.single_pair:
                report_update_result(
                    result,
                    messenger=messenger,
                    dataset_name=f"market history for region {region_id}, type {type_id}",
                )
            if not live and completed % options.worker_count == 0:
                messenger.print(
                    f"Completed {completed}/{len(type_ids)} pairs for {region_label}.",
                    markup=False,
                )

        return await bulk.update_market_histories(
            resources.esi_link,
            resources.esi_schema,
            resources.market_history_db_connection,
            region_ids={region_id},
            type_ids=type_ids,
            on_result=report,
            worker_count=options.worker_count,
            failure_limit=options.failure_limit,
        )
