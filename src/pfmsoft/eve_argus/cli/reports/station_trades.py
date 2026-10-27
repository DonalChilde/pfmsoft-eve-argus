"""Generate per-station trading reports from local read-only databases."""

import logging
import sqlite3
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from whenever import Instant

from pfmsoft.eve_argus.cli.helpers import (
    get_eve_argus_settings_from_context,
    get_static_database_path,
)
from pfmsoft.eve_argus.dynamic import read as dynamic_read
from pfmsoft.eve_argus.dynamic.models import MarketOrdersResponse
from pfmsoft.eve_argus.helpers.connection_helpers import db_connection_manager
from pfmsoft.eve_argus.helpers.file_safe_string import file_safe_string
from pfmsoft.eve_argus.market_history import read as history_read
from pfmsoft.eve_argus.market_history.models import MarketHistoryRecord
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS, MarketHub
from pfmsoft.eve_argus.reports.station_trades import (
    RegionalHistory,
    StationTradesOptions,
    StationTradesReport,
    collect_station_trades,
    select_history_window,
    validate_market_group_ids,
)
from pfmsoft.eve_argus.reports.station_trades_render import (
    render_station_trades_csv,
    render_station_trades_json,
    render_station_trades_markdown,
)
from pfmsoft.eve_argus.settings import EveArgusSettings
from pfmsoft.eve_argus.static import read as static_read

logger = logging.getLogger(__name__)
app = typer.Typer(no_args_is_help=True)

HISTORY_FETCH_HINT = (
    "Run 'eve-argus fetch market-history --hubs --market-types' to fetch history."
)


@dataclass(slots=True, kw_only=True, frozen=True)
class _HubSnapshot:
    """The latest regional order response selected for one hub."""

    hub: MarketHub
    response: MarketOrdersResponse


def _percent_option(help_text: str) -> typer.models.OptionInfo:
    """Build a 0-100 percent option."""
    return typer.Option(min=0, max=100, help=help_text)


@app.command(name="station-trades")
def station_trades(
    ctx: typer.Context,
    to: Annotated[
        Path,
        typer.Option("--to", help="Directory for per-station reports."),
    ],
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace existing report files.")
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Suppress progress, not errors or data warnings."),
    ] = False,
    buy_broker_fee: Annotated[
        float, _percent_option("Broker fee percent on the proposed buy order.")
    ] = 0.0,
    sell_broker_fee: Annotated[
        float, _percent_option("Broker fee percent on the proposed sell order.")
    ] = 0.0,
    sales_tax: Annotated[
        float, _percent_option("Sales tax percent of the gross sale value.")
    ] = 0.0,
    participation_percent: Annotated[
        float,
        _percent_option(
            "Assumed percent of regional daily volume completed (greater than 0)."
        ),
    ] = 1.0,
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
) -> None:
    """Find items to buy and relist at each hub's primary station.

    Writes per-station Markdown, CSV, and JSON reports from the latest stored
    regional orders and history, without fetching data. Rows are ranked by an
    estimated daily net profit from a share of regional traded volume.
    """
    try:
        options = StationTradesOptions(
            participation_percent=_decimal(participation_percent),
            acquisition_broker_fee_percent=_decimal(buy_broker_fee),
            sale_broker_fee_percent=_decimal(sell_broker_fee),
            sales_tax_percent=_decimal(sales_tax),
            include_market_group_ids=tuple(sorted(set(include or ()))),
            exclude_market_group_ids=tuple(sorted(set(exclude or ()))),
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    settings = get_eve_argus_settings_from_context(ctx)
    errors = Console(stderr=True)
    try:
        _generate_reports(
            settings=settings,
            destination=to,
            overwrite=overwrite,
            options=options,
            messenger=Console(stderr=True, quiet=quiet),
            errors=errors,
        )
    except (OSError, sqlite3.Error, ValueError) as error:
        logger.error("Station trades report failed: %s", error)
        errors.print(f"Error: {error}", markup=False, soft_wrap=True)
        raise typer.Exit(code=1) from error


def _decimal(value: float) -> Decimal:
    """Convert a CLI float without binary-float artifacts or a trailing `.0`."""
    return Decimal(int(value)) if value.is_integer() else Decimal(str(value))


def _select_snapshots(dynamic: sqlite3.Connection) -> list[_HubSnapshot]:
    """Select the latest regional order response for every hub.

    Raises:
        ValueError: If any hub has no stored orders.
    """
    responses_by_region = {
        region_id: dynamic_read.market_orders_responses(dynamic, region_id=region_id)
        for region_id in dict.fromkeys(hub.region_id for hub in MARKET_HUBS)
    }
    missing = [
        hub.system_name for hub in MARKET_HUBS if not responses_by_region[hub.region_id]
    ]
    if missing:
        raise ValueError(
            f"No stored regional market orders for: {', '.join(missing)}. "
            "Run 'eve-argus fetch market-orders --hubs' to fetch source orders."
        )
    return [
        _HubSnapshot(hub=hub, response=responses_by_region[hub.region_id][0])
        for hub in MARKET_HUBS
    ]


def _output_stems(
    *, destination: Path, snapshots: list[_HubSnapshot], overwrite: bool
) -> dict[int, Path]:
    """Name and preflight every output before any data is calculated.

    Returns:
        File stems keyed by station ID.

    Raises:
        ValueError: If a name is empty, collides, or exists without --overwrite.
    """
    stems: dict[int, Path] = {}
    paths: set[Path] = set()
    for snapshot in snapshots:
        hub = snapshot.hub
        name = file_safe_string(hub.system_name)
        timestamp = file_safe_string(snapshot.response.received_at)
        if not name or not timestamp:
            raise ValueError(
                f"Empty sanitized filename component for hub {hub.system_name}."
            )
        stem = destination / f"station-trades-{name}-{hub.station_id}-{timestamp}"
        stems[hub.station_id] = stem
        for suffix in (".md", ".csv", ".json"):
            path = stem.with_name(stem.name + suffix)
            if path in paths:
                raise ValueError(f"Report filename collision: {path}")
            paths.add(path)
            if path.exists() and (not overwrite or not path.is_file()):
                raise ValueError(
                    f"Report path already exists: {path}. "
                    "Use --overwrite to replace existing files."
                )
    return stems


def _regional_history(
    connection: sqlite3.Connection, *, region_id: int, generated_at: Instant
) -> RegionalHistory:
    """Select the region's common window and a cached records lookup."""
    generation_date = date.fromisoformat(generated_at.format_iso()[:10])
    newest = history_read.newest_history_date(
        connection, region_id=region_id, before=generation_date.isoformat()
    )
    window = (
        None
        if newest is None
        else select_history_window(
            newest_stored_date=newest, generation_date=generation_date
        )
    )

    def records(type_id: int) -> tuple[MarketHistoryRecord, ...]:
        if window is None:
            return ()
        return history_read.market_history_date_range(
            connection,
            region_id=region_id,
            type_id=type_id,
            start=window.newest_date,
            end=window.oldest_date,
        )

    return RegionalHistory(window=window, records=records)


def _warn(reports: list[StationTradesReport], errors: Console) -> None:
    """Print each distinct data warning once, naming the affected hubs.

    Data warnings remain visible with --quiet.
    """
    hubs_by_warning: dict[str, list[str]] = {}
    for report in reports:
        for warning in report.warnings:
            hubs_by_warning.setdefault(warning, []).append(report.hub.system_name)
    for warning, hubs in hubs_by_warning.items():
        errors.print(
            f"Warning [{', '.join(hubs)}]: {warning}", markup=False, soft_wrap=True
        )


def _generate_reports(
    *,
    settings: EveArgusSettings,
    destination: Path,
    overwrite: bool,
    options: StationTradesOptions,
    messenger: Console,
    errors: Console,
) -> None:
    """Preflight every hub, render all outputs, then write without refreshing data."""
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"Report destination is not a directory: {destination}")
    generated_at = Instant.now()
    outputs: dict[Path, str] = {}
    reports: list[StationTradesReport] = []
    with ExitStack() as stack:
        dynamic = stack.enter_context(
            db_connection_manager(settings.argus_dynamic_database, read_only=True)
        )
        static = stack.enter_context(
            db_connection_manager(get_static_database_path(settings), read_only=True)
        )
        market_groups = static_read.market_groups(static)
        try:
            validate_market_group_ids(
                market_groups,
                (*options.include_market_group_ids, *options.exclude_market_group_ids),
            )
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error
        snapshots = _select_snapshots(dynamic)
        stems = _output_stems(
            destination=destination, snapshots=snapshots, overwrite=overwrite
        )
        history: sqlite3.Connection | None = None
        if settings.market_history_database.is_file():
            history = stack.enter_context(
                db_connection_manager(settings.market_history_database, read_only=True)
            )
        else:
            errors.print(
                "Warning: market history database not found at "
                f"{settings.market_history_database}; daily estimates are unknown "
                f"and no rows are ranked. {HISTORY_FETCH_HINT}",
                markup=False,
                soft_wrap=True,
            )
        types = static_read.types(static, only_published=False)
        histories: dict[int, RegionalHistory | None] = {}
        for snapshot in snapshots:
            hub, response = snapshot.hub, snapshot.response
            messenger.print(
                f"Evaluating {hub.station_name} station trades from orders received "
                f"{response.received_at}...",
                markup=False,
                soft_wrap=True,
            )
            if hub.region_id not in histories:
                histories[hub.region_id] = (
                    None
                    if history is None
                    else _regional_history(
                        history, region_id=hub.region_id, generated_at=generated_at
                    )
                )
            orders = dynamic_read.market_orders(
                dynamic, response_metadata_id=response.response_metadata_id
            )
            report = collect_station_trades(
                hub=hub,
                response=response,
                orders=orders,
                types=types,
                market_groups=market_groups,
                history=histories[hub.region_id],
                options=options,
                generated_at=generated_at,
            )
            reports.append(report)
            stem = stems[hub.station_id]
            outputs[stem.with_name(stem.name + ".md")] = render_station_trades_markdown(
                report
            )
            outputs[stem.with_name(stem.name + ".csv")] = render_station_trades_csv(
                report
            )
            outputs[stem.with_name(stem.name + ".json")] = render_station_trades_json(
                report
            )
    _warn(reports, errors)
    destination.mkdir(parents=True, exist_ok=True)
    for path, content in outputs.items():
        with path.open(
            "w" if overwrite else "x", encoding="utf-8", newline=""
        ) as stream:
            stream.write(content)
        messenger.print(f"Wrote {path}", markup=False, soft_wrap=True)
