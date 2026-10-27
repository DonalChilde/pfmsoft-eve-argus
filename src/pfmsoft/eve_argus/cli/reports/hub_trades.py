"""Generate per-source hub-to-hub trade reports from local read-only databases."""

import logging
import sqlite3
from contextlib import ExitStack
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from whenever import Instant

from pfmsoft.eve_argus.cli.helpers import (
    get_eve_argus_settings_from_context,
    get_static_database_path,
)
from pfmsoft.eve_argus.cli.reports._hub_snapshots import (
    HubSnapshot,
    option_decimal,
    percent_option,
    select_hub_snapshots,
)
from pfmsoft.eve_argus.dynamic import read as dynamic_read
from pfmsoft.eve_argus.helpers.connection_helpers import db_connection_manager
from pfmsoft.eve_argus.helpers.file_safe_string import file_safe_string
from pfmsoft.eve_argus.reports.hub_trades import (
    HubStationBooks,
    HubTradesOptions,
    HubTradesReport,
    build_station_books,
    collect_hub_trades,
)
from pfmsoft.eve_argus.reports.hub_trades_render import (
    render_hub_trades_csv,
    render_hub_trades_json,
    render_hub_trades_markdown,
)
from pfmsoft.eve_argus.reports.station_trades import validate_market_group_ids
from pfmsoft.eve_argus.settings import EveArgusSettings
from pfmsoft.eve_argus.static import read as static_read

logger = logging.getLogger(__name__)
app = typer.Typer(no_args_is_help=True)


@app.command(name="hub-trades")
def hub_trades(
    ctx: typer.Context,
    to: Annotated[
        Path,
        typer.Option("--to", help="Directory for per-source reports."),
    ],
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace existing report files.")
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Suppress progress, not errors or data warnings."),
    ] = False,
    sales_tax: Annotated[
        float, percent_option("Sales tax percent of the gross sale value.")
    ] = 0.0,
    transport_per_m3: Annotated[
        float,
        typer.Option("--transport-per-m3", min=0, help="Transport cost in ISK per m³."),
    ] = 0.0,
    min_profit: Annotated[
        float,
        typer.Option(
            "--min-profit", min=0, help="Rank rows with net profit above this ISK."
        ),
    ] = 0.0,
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
    """Find items to buy at one hub's station and sell into another hub's buy orders.

    Writes one Markdown, CSV, and JSON report per source station from the latest
    stored regional orders, without fetching data. Quantities walk both order
    books; rows are ranked by net profit after sales tax and transport.
    """
    try:
        options = HubTradesOptions(
            sales_tax_percent=option_decimal(sales_tax),
            transport_per_m3=option_decimal(transport_per_m3),
            min_profit=option_decimal(min_profit),
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
        logger.error("Hub trades report failed: %s", error)
        errors.print(f"Error: {error}", markup=False, soft_wrap=True)
        raise typer.Exit(code=1) from error


def _output_stems(
    *,
    destination: Path,
    snapshots: list[HubSnapshot],
    generated_at: Instant,
    overwrite: bool,
) -> dict[int, Path]:
    """Name and preflight every output before any data is calculated.

    Returns:
        File stems keyed by source station ID.

    Raises:
        ValueError: If a name is empty, collides, or exists without --overwrite.
    """
    timestamp = file_safe_string(generated_at.format_iso())
    stems: dict[int, Path] = {}
    paths: set[Path] = set()
    for snapshot in snapshots:
        hub = snapshot.hub
        name = file_safe_string(hub.system_name)
        if not name or not timestamp:
            raise ValueError(
                f"Empty sanitized filename component for hub {hub.system_name}."
            )
        stem = destination / f"hub-trades-from-{name}-{hub.station_id}-{timestamp}"
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


def _warn(reports: list[HubTradesReport], errors: Console) -> None:
    """Print each distinct data warning once, naming the affected source hubs.

    Data warnings remain visible with --quiet.
    """
    hubs_by_warning: dict[str, list[str]] = {}
    for report in reports:
        for warning in report.warnings:
            hubs_by_warning.setdefault(warning, []).append(
                report.source.hub.system_name
            )
    for warning, hubs in hubs_by_warning.items():
        errors.print(
            f"Warning [{', '.join(hubs)}]: {warning}", markup=False, soft_wrap=True
        )


def _generate_reports(
    *,
    settings: EveArgusSettings,
    destination: Path,
    overwrite: bool,
    options: HubTradesOptions,
    messenger: Console,
    errors: Console,
) -> None:
    """Preflight every source, render all outputs, then write without refreshing."""
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"Report destination is not a directory: {destination}")
    generated_at = Instant.now()
    outputs: dict[Path, str] = {}
    reports: list[HubTradesReport] = []
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
        snapshots = select_hub_snapshots(dynamic)
        stems = _output_stems(
            destination=destination,
            snapshots=snapshots,
            generated_at=generated_at,
            overwrite=overwrite,
        )
        types = static_read.types(static, only_published=False)
        books: list[HubStationBooks] = []
        for snapshot in snapshots:
            messenger.print(
                f"Reading {snapshot.hub.station_name} orders received "
                f"{snapshot.response.received_at}...",
                markup=False,
                soft_wrap=True,
            )
            books.append(
                build_station_books(
                    hub=snapshot.hub,
                    response=snapshot.response,
                    orders=dynamic_read.market_orders(
                        dynamic,
                        response_metadata_id=snapshot.response.response_metadata_id,
                    ),
                )
            )
    for source in books:
        messenger.print(
            f"Matching trades from {source.hub.station_name}...",
            markup=False,
            soft_wrap=True,
        )
        report = collect_hub_trades(
            source=source,
            destinations=[item for item in books if item is not source],
            types=types,
            market_groups=market_groups,
            options=options,
            generated_at=generated_at,
        )
        reports.append(report)
        stem = stems[source.hub.station_id]
        outputs[stem.with_name(stem.name + ".md")] = render_hub_trades_markdown(report)
        outputs[stem.with_name(stem.name + ".csv")] = render_hub_trades_csv(report)
        outputs[stem.with_name(stem.name + ".json")] = render_hub_trades_json(report)
    _warn(reports, errors)
    destination.mkdir(parents=True, exist_ok=True)
    for path, content in outputs.items():
        with path.open(
            "w" if overwrite else "x", encoding="utf-8", newline=""
        ) as stream:
            stream.write(content)
        messenger.print(f"Wrote {path}", markup=False, soft_wrap=True)
