"""Calculate market hub system prices on demand from local read-only databases."""

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
from pfmsoft.eve_argus.dynamic.order_summary import (
    FILTER_FACTOR_DEFAULT,
    calculate_dataset_summaries,
)
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
    """Calculate and export hub system prices from the latest stored orders, offline."""
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
        responses_by_region = {
            region_id: dynamic_read.market_orders_responses(
                dynamic, region_id=region_id
            )
            for region_id in dict.fromkeys(hub.region_id for hub in MARKET_HUBS)
        }
        selected = [
            (
                hub,
                responses[0]
                if (responses := responses_by_region[hub.region_id])
                else None,
            )
            for hub in MARKET_HUBS
        ]
        missing = [hub.system_name for hub, response in selected if response is None]
        if missing:
            raise ValueError(
                f"No stored regional market orders for: {', '.join(missing)}. "
                "Run 'eve-argus fetch market-orders --hubs' to fetch source orders."
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
        for region_id in responses_by_region:
            region_hubs = [
                (hub, response)
                for hub, response in selected
                if hub.region_id == region_id
            ]
            response = region_hubs[0][1]
            assert response is not None
            orders = dynamic_read.market_orders(
                dynamic, response_metadata_id=response.response_metadata_id
            )
            for hub, response in region_hubs:
                assert response is not None
                messenger.print(
                    f"Calculating {hub.system_name} prices from orders received "
                    f"{response.received_at}...",
                    markup=False,
                )
                report = collect_market_hub_prices(
                    summaries=calculate_dataset_summaries(
                        orders,
                        system_id=hub.system_id,
                        filter_factor=FILTER_FACTOR_DEFAULT,
                    ),
                    response=response,
                    hub=hub,
                    types=types,
                    market_groups=market_groups,
                    generated_at=generated_at,
                    filter_factor=FILTER_FACTOR_DEFAULT,
                )
                if report.is_stale:
                    errors.print(
                        f"Warning: the stored {hub.system_name} order snapshot has "
                        "expired; it was not refreshed.",
                        markup=False,
                    )
                stem = (
                    f"price-summary-{file_safe_string(hub.system_name)}-"
                    f"{file_safe_string(response.received_at)}"
                )
                outputs[destination / f"{stem}.csv"] = render_market_hub_prices_csv(
                    report
                )
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
