"""Generate per-region summaries from stored market history."""

import logging
import sqlite3
from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from whenever import Instant

from pfmsoft.eve_argus.cli.helpers import (
    get_eve_argus_settings_from_context,
    get_static_database_path,
)
from pfmsoft.eve_argus.helpers.connection_helpers import db_connection_manager
from pfmsoft.eve_argus.helpers.file_safe_string import file_safe_string
from pfmsoft.eve_argus.market_history import read as history_read
from pfmsoft.eve_argus.market_history.helpers import first_possible_date
from pfmsoft.eve_argus.market_history.history_summary import date_range_days
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS
from pfmsoft.eve_argus.reports.history_summary import (
    HistorySummaryInput,
    HistorySummaryReport,
    collect_history_summary_report,
)
from pfmsoft.eve_argus.reports.history_summary_render import (
    render_history_summary_csv,
    render_history_summary_json,
)
from pfmsoft.eve_argus.settings import EveArgusSettings
from pfmsoft.eve_argus.static import read as static_read
from pfmsoft.eve_argus.static.models import MapRegionsDataset

logger = logging.getLogger(__name__)
app = typer.Typer(no_args_is_help=True)


@app.command(name="history-summary")
def history_summary(
    ctx: typer.Context,
    to: Annotated[
        Path,
        typer.Option("--to", help="Directory for per-region CSV and JSON reports."),
    ],
    region_id: Annotated[
        list[int] | None,
        typer.Option("--region-id", help="Region ID; repeat to select multiple."),
    ] = None,
    period: Annotated[
        int,
        typer.Option("--period", min=1, help="Number of calendar days per summary."),
    ] = 10,
    start_date: Annotated[
        str | None,
        typer.Option(
            "--start-date",
            help=(
                "Newest date in each window, inclusive, in YYYY-MM-DD format. "
                "The period counts backward from this date."
            ),
        ),
    ] = None,
    hubs: Annotated[
        bool,
        typer.Option("--hubs", help="Append the configured market-hub regions."),
    ] = False,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace existing report files.")
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Suppress progress, not warnings or errors."),
    ] = False,
) -> None:
    """Summarize stored regional market history over a date window."""
    if not region_id and not hubs:
        raise typer.BadParameter("Select at least one --region-id or use --hubs.")
    if start_date is not None:
        try:
            if date.fromisoformat(start_date).isoformat() != start_date:
                raise ValueError("Use YYYY-MM-DD.")
        except ValueError as error:
            raise typer.BadParameter(
                f"Invalid --start-date {start_date!r}; use YYYY-MM-DD.",
                param_hint="--start-date",
            ) from error
        today = Instant.now().format_iso()[:10]
        if start_date > today:
            raise typer.BadParameter(
                "--start-date cannot be in the future.", param_hint="--start-date"
            )

    settings = get_eve_argus_settings_from_context(ctx)
    errors = Console(stderr=True)
    try:
        _generate_reports(
            settings=settings,
            destination=to,
            region_ids=region_id or [],
            period_days=period,
            start_date=start_date,
            hubs=hubs,
            overwrite=overwrite,
            messenger=Console(stderr=True, quiet=quiet),
            errors=errors,
        )
    except (OSError, sqlite3.Error, ValueError) as error:
        logger.error("History summary export failed: %s", error)
        errors.print(f"Error: {error}", markup=False, soft_wrap=True)
        raise typer.Exit(code=1) from error


def _selected_regions(
    *,
    region_ids: list[int],
    hubs: bool,
    regions: MapRegionsDataset,
) -> list[tuple[int, str]]:
    """Resolve explicit and hub regions, preserving order and removing duplicates."""
    selected_ids = list(region_ids)
    if hubs:
        selected_ids.extend(hub.region_id for hub in MARKET_HUBS)
    selected: list[tuple[int, str]] = []
    seen: set[int] = set()
    for selected_region_id in selected_ids:
        if selected_region_id <= 0 or selected_region_id not in regions:
            raise typer.BadParameter(
                f"Unknown or invalid region ID {selected_region_id}.",
                param_hint="--region-id",
            )
        if selected_region_id not in seen:
            selected.append((selected_region_id, regions[selected_region_id].name))
            seen.add(selected_region_id)
    return selected


def _history_inputs(
    *,
    connection: sqlite3.Connection,
    region_id: int,
    type_ids: tuple[int, ...],
    period_days: int,
    start_date: str | None,
) -> tuple[HistorySummaryInput, ...]:
    """Read each type's independent window plus latest metadata for empty windows."""
    inputs: list[HistorySummaryInput] = []
    for type_id in sorted(type_ids):
        latest = history_read.market_history(
            connection, region_id=region_id, type_id=type_id, count=1
        )
        latest_record = latest[0] if latest else None
        selected_start = start_date
        if selected_start is None and latest_record is not None:
            selected_start = first_possible_date(latest_record.received_at)
        dates = (
            tuple(date_range_days(selected_start, period_days))
            if selected_start is not None
            else ()
        )
        records = (
            history_read.market_history_date_range(
                connection,
                region_id=region_id,
                type_id=type_id,
                start=dates[0],
                end=dates[-1],
            )
            if dates
            else ()
        )
        inputs.append(
            HistorySummaryInput(
                type_id=type_id,
                dates=dates,
                records=records,
                latest_record=latest_record,
            )
        )
    return tuple(inputs)


def _output_stems(
    *,
    destination: Path,
    reports: tuple[HistorySummaryReport, ...],
    generated_at: Instant,
    overwrite: bool,
) -> dict[int, Path]:
    """Build and preflight output paths for every selected region."""
    generated_timestamp = file_safe_string(generated_at.format_iso())
    paths: set[Path] = set()
    stems: dict[int, Path] = {}
    for report in reports:
        region_name = file_safe_string(report.region_name)
        start_label = report.start_date or "latest"
        stem = destination / (
            f"history-summary-{region_name}-{report.period_days}d-"
            f"{start_label}-{generated_timestamp}"
        )
        if not region_name or not generated_timestamp:
            raise ValueError(
                f"Empty sanitized filename component for region {report.region_name}."
            )
        stems[report.region_id] = stem
        for suffix in (".csv", ".json"):
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


def _warn_stale_rows(
    reports: tuple[HistorySummaryReport, ...], errors: Console
) -> None:
    """Keep per-type stale-history warnings visible even when progress is quiet."""
    for report in reports:
        stale_types = [
            f"{row.type_name} ({row.type_id})"
            for row in report.records
            if row.is_stale is True
        ]
        if stale_types:
            errors.print(
                f"Warning: stored market history is expired for {report.region_name}: "
                f"{', '.join(stale_types)}.",
                markup=False,
                soft_wrap=True,
            )


def _generate_reports(
    *,
    settings: EveArgusSettings,
    destination: Path,
    region_ids: list[int],
    period_days: int,
    start_date: str | None,
    hubs: bool,
    overwrite: bool,
    messenger: Console,
    errors: Console,
) -> None:
    """Collect and render every selected region before writing any report files."""
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"Report destination is not a directory: {destination}")
    if not settings.market_history_database.is_file():
        raise FileNotFoundError(
            f"Market history database not found at {settings.market_history_database}. "
            "Fetch source data with 'eve-argus fetch market-history'."
        )
    generated_at = Instant.now()
    outputs: dict[Path, str] = {}
    with (
        db_connection_manager(
            settings.market_history_database, read_only=True
        ) as history,
        db_connection_manager(
            get_static_database_path(settings), read_only=True
        ) as static,
    ):
        regions = static_read.map_regions(static)
        selected_regions = _selected_regions(
            region_ids=region_ids, hubs=hubs, regions=regions
        )
        types = static_read.types(static, only_published=False)
        market_groups = static_read.market_groups(static)
        reports: list[HistorySummaryReport] = []
        for selected_region_id, region_name in selected_regions:
            messenger.print(
                f"Summarizing market history for {region_name} ({selected_region_id})...",
                markup=False,
            )
            type_ids = history_read.types_in_region(
                history, region_id=selected_region_id
            )
            if not type_ids:
                errors.print(
                    f"Warning: no stored market history for {region_name} "
                    f"({selected_region_id}). Fetch source data with "
                    f"'eve-argus fetch market-history --region-id {selected_region_id} "
                    "--market-types'.",
                    markup=False,
                    soft_wrap=True,
                )
            inputs = _history_inputs(
                connection=history,
                region_id=selected_region_id,
                type_ids=type_ids,
                period_days=period_days,
                start_date=start_date,
            )
            reports.append(
                collect_history_summary_report(
                    region_id=selected_region_id,
                    region_name=region_name,
                    period_days=period_days,
                    start_date=start_date,
                    summaries=inputs,
                    types=types,
                    market_groups=market_groups,
                    generated_at=generated_at,
                )
            )
        report_tuple = tuple(reports)
        _warn_stale_rows(report_tuple, errors)
        stems = _output_stems(
            destination=destination,
            reports=report_tuple,
            generated_at=generated_at,
            overwrite=overwrite,
        )
        for report in report_tuple:
            stem = stems[report.region_id]
            outputs[stem.with_name(stem.name + ".csv")] = render_history_summary_csv(
                report
            )
            outputs[stem.with_name(stem.name + ".json")] = render_history_summary_json(
                report
            )

    destination.mkdir(parents=True, exist_ok=True)
    for path, content in outputs.items():
        with path.open(
            "w" if overwrite else "x", encoding="utf-8", newline=""
        ) as stream:
            stream.write(content)
        messenger.print(f"Wrote {path}", markup=False)
