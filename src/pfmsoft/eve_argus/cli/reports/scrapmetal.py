"""Generate per-hub scrapmetal reprocessing reports from local read-only databases."""

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
from pfmsoft.eve_argus.dynamic.order_summary import calculate_dataset_summaries
from pfmsoft.eve_argus.helpers.connection_helpers import db_connection_manager
from pfmsoft.eve_argus.helpers.file_safe_string import file_safe_string
from pfmsoft.eve_argus.market_history import read as history_read
from pfmsoft.eve_argus.market_history.models import HistorySummaryRecord
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS, MarketHub
from pfmsoft.eve_argus.reports.scrapmetal import (
    HISTORY_STALE_DAYS,
    HistoryLookup,
    HubPriceInputs,
    ScrapmetalOptions,
    collect_scrapmetal_deals,
    collect_scrapmetal_price_points,
)
from pfmsoft.eve_argus.reports.scrapmetal_render import (
    render_scrapmetal_deals_csv,
    render_scrapmetal_deals_json,
    render_scrapmetal_deals_markdown,
    render_scrapmetal_price_points_csv,
    render_scrapmetal_price_points_json,
)
from pfmsoft.eve_argus.settings import EveArgusSettings
from pfmsoft.eve_argus.static import read as static_read

logger = logging.getLogger(__name__)
app = typer.Typer(no_args_is_help=True)

HISTORY_FETCH_HINT = (
    "Run 'eve-argus fetch market-history --hubs --scrapmetal' to fetch history."
)


@dataclass(slots=True, kw_only=True, frozen=True)
class _HubSnapshot:
    """The latest regional order response selected for one hub."""

    hub: MarketHub
    response: MarketOrdersResponse


def _percent_option(help_text: str) -> typer.models.OptionInfo:
    return typer.Option(min=0, max=100, help=help_text)


@app.command(name="scrapmetal")
def scrapmetal(
    ctx: typer.Context,
    to: Annotated[
        Path,
        typer.Option("--to", help="Directory for per-hub deals and price points."),
    ],
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace existing report files.")
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Suppress progress, not errors or data warnings."),
    ] = False,
    yield_percent: Annotated[
        float, _percent_option("Reprocessing yield percent.")
    ] = 55.0,
    reprocessing_tax: Annotated[
        float, _percent_option("Reprocessing tax percent of gross material value.")
    ] = 0.0,
    sales_tax: Annotated[
        float, _percent_option("Sales tax percent of gross material value.")
    ] = 0.0,
    broker_fee: Annotated[
        float,
        _percent_option("Listing cost percent; applies to the sell-order table only."),
    ] = 0.0,
    min_profit: Annotated[
        float, typer.Option(min=0, help="Minimum total profit (ISK) to rank a deal.")
    ] = 100_000.0,
    min_margin: Annotated[
        float, typer.Option(min=0, help="Minimum margin percent to buy and rank.")
    ] = 5.0,
    max_slippage: Annotated[
        float,
        typer.Option(min=0, help="Maximum immediate output slippage percent."),
    ] = 10.0,
) -> None:
    """Find hub items to buy and reprocess for profit, and sourcing price points.

    Writes per-hub deal reports (Markdown, CSV, JSON) and one price-point list
    (CSV, JSON) from the latest stored orders and history, without fetching data.
    """
    settings = get_eve_argus_settings_from_context(ctx)
    errors = Console(stderr=True)
    try:
        options = ScrapmetalOptions(
            yield_percent=_decimal(yield_percent),
            reprocessing_tax=_decimal(reprocessing_tax),
            sales_tax=_decimal(sales_tax),
            broker_fee=_decimal(broker_fee),
            min_profit=_decimal(min_profit),
            min_margin=_decimal(min_margin),
            max_slippage=_decimal(max_slippage),
        )
        _generate_reports(
            settings=settings,
            destination=to,
            overwrite=overwrite,
            options=options,
            messenger=Console(stderr=True, quiet=quiet),
            errors=errors,
        )
    except (OSError, sqlite3.Error, ValueError) as error:
        logger.error("Scrapmetal report failed: %s", error)
        errors.print(f"Error: {error}", markup=False, soft_wrap=True)
        raise typer.Exit(code=1) from error


def _decimal(value: float) -> Decimal:
    """Convert a CLI float without binary-float artifacts or a trailing `.0`."""
    return Decimal(int(value)) if value.is_integer() else Decimal(str(value))


def _history_lookup(connection: sqlite3.Connection, region_id: int) -> HistoryLookup:
    """Build a cached regional history lookup; unusable history counts as missing."""
    cache: dict[int, HistorySummaryRecord | None] = {}

    def lookup(type_id: int) -> HistorySummaryRecord | None:
        if type_id not in cache:
            try:
                cache[type_id] = history_read.history_summary(
                    connection, region_id=region_id, type_id=type_id
                )
            except ValueError as error:
                logger.info(
                    "No usable history for type %s in region %s: %s",
                    type_id,
                    region_id,
                    error,
                )
                cache[type_id] = None
        return cache[type_id]

    return lookup


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


def _output_paths(
    *,
    destination: Path,
    snapshots: list[_HubSnapshot],
    generated_at: Instant,
    overwrite: bool,
) -> tuple[dict[str, Path], Path]:
    """Name and preflight every output before any data is calculated.

    Returns:
        Per-hub deal file stems keyed by hub name, and the price-point file stem.

    Raises:
        ValueError: If a name is empty, collides, or exists without --overwrite.
    """
    stems: dict[str, Path] = {}
    for snapshot in snapshots:
        name = file_safe_string(snapshot.hub.system_name)
        timestamp = file_safe_string(snapshot.response.received_at)
        if not name or not timestamp:
            raise ValueError(
                f"Empty sanitized filename component for hub {snapshot.hub.system_name}."
            )
        stems[snapshot.hub.system_name] = (
            destination / f"scrapmetal-deals-{name}-{timestamp}"
        )
    price_points = (
        destination
        / f"scrapmetal-price-points-{file_safe_string(generated_at.format_iso())}"
    )
    paths: set[Path] = set()
    for stem, suffixes in [
        *((stem, (".md", ".csv", ".json")) for stem in stems.values()),
        (price_points, (".csv", ".json")),
    ]:
        for suffix in suffixes:
            path = stem.with_name(stem.name + suffix)
            if path in paths:
                raise ValueError(f"Report filename collision: {path}")
            paths.add(path)
            if path.exists() and (not overwrite or not path.is_file()):
                raise ValueError(
                    f"Report path already exists: {path}. "
                    "Use --overwrite to replace existing files."
                )
    return stems, price_points


def _warn_history(
    *,
    hub: MarketHub,
    newest: str | None,
    generated_at: Instant,
    errors: Console,
) -> None:
    """Warn when a hub has no usable or only stale history."""
    if newest is None:
        errors.print(
            f"Warning: No market history for {hub.system_name} scrapmetal items; "
            f"history context is omitted. {HISTORY_FETCH_HINT}",
            markup=False,
            soft_wrap=True,
        )
        return
    age = (
        date.fromisoformat(generated_at.format_iso()[:10]) - date.fromisoformat(newest)
    ).days
    if age > HISTORY_STALE_DAYS:
        errors.print(
            f"Warning: {hub.system_name} market history ends {newest}, "
            f"{age} days ago. {HISTORY_FETCH_HINT}",
            markup=False,
            soft_wrap=True,
        )


def _generate_reports(
    *,
    settings: EveArgusSettings,
    destination: Path,
    overwrite: bool,
    options: ScrapmetalOptions,
    messenger: Console,
    errors: Console,
) -> None:
    """Preflight every hub, render all outputs, then write without refreshing data."""
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"Report destination is not a directory: {destination}")
    generated_at = Instant.now()
    outputs: dict[Path, str] = {}
    with ExitStack() as stack:
        dynamic = stack.enter_context(
            db_connection_manager(settings.argus_dynamic_database, read_only=True)
        )
        static = stack.enter_context(
            db_connection_manager(get_static_database_path(settings), read_only=True)
        )
        snapshots = _select_snapshots(dynamic)
        stems, price_points_stem = _output_paths(
            destination=destination,
            snapshots=snapshots,
            generated_at=generated_at,
            overwrite=overwrite,
        )
        history: sqlite3.Connection | None = None
        if settings.market_history_database.is_file():
            history = stack.enter_context(
                db_connection_manager(settings.market_history_database, read_only=True)
            )
        else:
            errors.print(
                "Warning: market history database not found at "
                f"{settings.market_history_database}; history context and "
                f"price-point history values are omitted. {HISTORY_FETCH_HINT}",
                markup=False,
                soft_wrap=True,
            )
        types = static_read.types(static, only_published=False)
        type_materials = static_read.type_materials(static)
        market_groups = static_read.market_groups(static)
        price_inputs: list[HubPriceInputs] = []
        for snapshot in snapshots:
            hub, response = snapshot.hub, snapshot.response
            messenger.print(
                f"Evaluating {hub.system_name} scrapmetal deals from orders received "
                f"{response.received_at}...",
                markup=False,
                soft_wrap=True,
            )
            orders = dynamic_read.market_orders(
                dynamic, response_metadata_id=response.response_metadata_id
            )
            summaries = calculate_dataset_summaries(orders, system_id=hub.system_id)
            lookup = (
                _history_lookup(history, hub.region_id) if history is not None else None
            )
            report = collect_scrapmetal_deals(
                hub=hub,
                response=response,
                orders=orders,
                summaries=summaries,
                types=types,
                type_materials=type_materials,
                market_groups=market_groups,
                history=lookup,
                options=options,
                generated_at=generated_at,
            )
            if report.is_stale:
                errors.print(
                    f"Warning: the stored {hub.system_name} order snapshot has "
                    "expired; it was not refreshed.",
                    markup=False,
                    soft_wrap=True,
                )
            stem = stems[hub.system_name]
            outputs[stem.with_name(stem.name + ".md")] = (
                render_scrapmetal_deals_markdown(report)
            )
            outputs[stem.with_name(stem.name + ".csv")] = render_scrapmetal_deals_csv(
                report
            )
            outputs[stem.with_name(stem.name + ".json")] = render_scrapmetal_deals_json(
                report
            )
            price_inputs.append(
                HubPriceInputs(
                    hub=hub, response=response, summaries=summaries, history=lookup
                )
            )
        messenger.print(
            "Calculating scrapmetal price points...", markup=False, soft_wrap=True
        )
        price_points = collect_scrapmetal_price_points(
            hubs=price_inputs,
            types=types,
            type_materials=type_materials,
            market_groups=market_groups,
            yield_percent=options.yield_percent,
            generated_at=generated_at,
        )
        if history is not None:
            for source, snapshot in zip(price_points.hubs, snapshots, strict=True):
                _warn_history(
                    hub=snapshot.hub,
                    newest=source.history_newest_date,
                    generated_at=generated_at,
                    errors=errors,
                )
        outputs[price_points_stem.with_name(price_points_stem.name + ".csv")] = (
            render_scrapmetal_price_points_csv(price_points)
        )
        outputs[price_points_stem.with_name(price_points_stem.name + ".json")] = (
            render_scrapmetal_price_points_json(price_points)
        )
    destination.mkdir(parents=True, exist_ok=True)
    for path, content in outputs.items():
        with path.open(
            "w" if overwrite else "x", encoding="utf-8", newline=""
        ) as stream:
            stream.write(content)
        messenger.print(f"Wrote {path}", markup=False, soft_wrap=True)
