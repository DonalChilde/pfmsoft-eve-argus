"""Export stored market hub system prices using only local read-only databases."""

import logging
import sqlite3
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
from pfmsoft.eve_argus.helpers.connection_helpers import db_connection_manager
from pfmsoft.eve_argus.helpers.file_safe_string import file_safe_string
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS
from pfmsoft.eve_argus.reports.market_hub_prices import collect_market_hub_prices
from pfmsoft.eve_argus.reports.market_hub_prices_render import (
    render_market_hub_prices_csv,
    render_market_hub_prices_json,
)
from pfmsoft.eve_argus.settings import EveArgusSettings
from pfmsoft.eve_argus.static import read as static_read

logger = logging.getLogger(__name__)
app = typer.Typer(no_args_is_help=True)


@app.command(name="hub-prices")
def hub_prices(
    ctx: typer.Context,
    to: Annotated[
        Path, typer.Option("--to", help="Directory for per-hub CSV and JSON.")
    ],
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace existing export files.")
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet", help="Suppress progress, not errors or stale-data warnings."
        ),
    ] = False,
) -> None:
    """Export latest stored system price summaries for all configured hubs, offline."""
    settings = get_eve_argus_settings_from_context(ctx)
    errors = Console(stderr=True)
    try:
        _generate_reports(
            settings=settings,
            destination=to,
            overwrite=overwrite,
            messenger=Console(stderr=True, quiet=quiet),
            errors=errors,
        )
    except (OSError, sqlite3.Error, ValueError) as error:
        logger.error("Market hub price export failed: %s", error)
        errors.print(f"Error: {error}", markup=False)
        raise typer.Exit(code=1) from error


def _generate_reports(
    *,
    settings: EveArgusSettings,
    destination: Path,
    overwrite: bool,
    messenger: Console,
    errors: Console,
) -> None:
    """Preflight every hub, render all outputs, then write without refreshing data."""
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"Report destination is not a directory: {destination}")
    generated_at = Instant.now()
    outputs: dict[Path, str] = {}
    with (
        db_connection_manager(
            settings.argus_dynamic_database, read_only=True
        ) as dynamic,
        db_connection_manager(
            get_static_database_path(settings), read_only=True
        ) as static,
    ):
        selected = [
            (
                hub,
                next(
                    (
                        response
                        for response in dynamic_read.order_summary_responses(
                            dynamic, region_id=hub.region_id
                        )
                        if response.region_id == hub.region_id
                        and response.system_id == hub.system_id
                        and response.location_id is None
                    ),
                    None,
                ),
            )
            for hub in MARKET_HUBS
        ]
        missing = [hub.system_name for hub, response in selected if response is None]
        if missing:
            raise ValueError(
                f"No stored system price summary for: {', '.join(missing)}. "
                "Summaries are saved by 'eve-argus fetch hub-orders' when new order "
                "data arrives; a cached fetch may not recreate missing summaries. "
                "Fetch again once fresh order data is available."
            )
        paths: set[Path] = set()
        for hub, response in selected:
            assert response is not None
            name = file_safe_string(hub.system_name)
            timestamp = file_safe_string(response.received_at)
            if not name or not timestamp:
                raise ValueError(
                    f"Empty sanitized filename component for hub {hub.system_name}."
                )
            for suffix in (".csv", ".json"):
                path = destination / f"price-summary-{name}-{timestamp}{suffix}"
                if path in paths:
                    raise ValueError(f"Hub export filename collision: {path}")
                paths.add(path)
                if path.exists() and (not overwrite or not path.is_file()):
                    raise ValueError(
                        f"Report path already exists: {path}. "
                        "Use --overwrite to replace existing files."
                    )
        types = static_read.types(static, only_published=False)
        market_groups = static_read.market_groups(static)
        for hub, response in selected:
            assert response is not None
            messenger.print(
                f"Reading {hub.system_name} snapshot received {response.received_at}...",
                markup=False,
            )
            report = collect_market_hub_prices(
                summaries=dynamic_read.order_summaries(
                    dynamic,
                    order_summary_response_id=response.order_summary_response_id,
                ),
                response=response,
                hub=hub,
                types=types,
                market_groups=market_groups,
                generated_at=generated_at,
            )
            if report.is_stale:
                errors.print(
                    f"Warning: the stored {hub.system_name} price snapshot has expired; "
                    "it was not refreshed.",
                    markup=False,
                )
            stem = (
                f"price-summary-{file_safe_string(hub.system_name)}-"
                f"{file_safe_string(response.received_at)}"
            )
            outputs[destination / f"{stem}.csv"] = render_market_hub_prices_csv(report)
            outputs[destination / f"{stem}.json"] = render_market_hub_prices_json(
                report
            )
    destination.mkdir(parents=True, exist_ok=True)
    for path, content in outputs.items():
        with path.open(
            "w" if overwrite else "x", encoding="utf-8", newline=""
        ) as stream:
            stream.write(content)
        messenger.print(f"Wrote {path}", markup=False)
