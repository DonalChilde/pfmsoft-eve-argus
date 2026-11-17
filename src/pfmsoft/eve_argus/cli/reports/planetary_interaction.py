"""Generate an offline PI scenario browser from stored Jita orders and history."""

import logging
import sqlite3
from contextlib import ExitStack
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated

import typer
from jinja2 import TemplateError
from rich.console import Console
from whenever import Instant

from pfmsoft.eve_argus.cli.helpers import get_eve_argus_settings_from_context
from pfmsoft.eve_argus.dynamic import read as dynamic_read
from pfmsoft.eve_argus.dynamic.models import BuySellOrders, MarketOrdersDataset
from pfmsoft.eve_argus.helpers.connection_helpers import db_connection_manager
from pfmsoft.eve_argus.market_history import read as history_read
from pfmsoft.eve_argus.market_history.models import MarketHistoryRecord
from pfmsoft.eve_argus.pi.catalog import load_catalog
from pfmsoft.eve_argus.pi.models import CostBoundary, validate_tax_rate
from pfmsoft.eve_argus.reports.pi_browser import (
    PiMarketInputs,
    collect_pi_market_inputs,
    resolve_jita_hub,
)
from pfmsoft.eve_argus.reports.pi_browser_render import BROWSER_FILES, render_pi_browser
from pfmsoft.eve_argus.reports.station_trades import (
    RegionalHistory,
    select_history_window,
)
from pfmsoft.eve_argus.settings import EveArgusSettings

logger = logging.getLogger(__name__)
app = typer.Typer(no_args_is_help=True)


@app.command(name="planetary-interaction")
def planetary_interaction(
    ctx: typer.Context,
    to: Annotated[
        Path,
        typer.Option("--to", help="Directory for index.html and local browser assets."),
    ],
    tax_percent: Annotated[
        str,
        typer.Option(
            "--tax-percent", help="Initial effective customs tax: 6 means 6%."
        ),
    ] = "6",
    intermediate_boundary: Annotated[
        CostBoundary,
        typer.Option(
            "--intermediate-boundary",
            help="Expanded intermediate output stays local or is exported/reimported.",
        ),
    ] = CostBoundary.ON_PLANET,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace existing generated files only.")
    ] = False,
    quiet: Annotated[
        bool, typer.Option("--quiet", help="Suppress progress, not warnings or errors.")
    ] = False,
) -> None:
    """Generate an offline HTML PI browser; never fetch or refresh source data."""
    try:
        rate = Decimal(tax_percent) / 100
        validate_tax_rate(rate)
    except (InvalidOperation, ValueError) as error:
        raise typer.BadParameter(
            "Tax must be a finite decimal percentage from 0 to 100.",
            param_hint="--tax-percent",
        ) from error
    settings = get_eve_argus_settings_from_context(ctx)
    errors = Console(stderr=True)
    try:
        _generate_browser(
            settings=settings,
            destination=to,
            tax_rate=rate,
            intermediate_boundary=intermediate_boundary,
            overwrite=overwrite,
            messenger=Console(stderr=True, quiet=quiet),
            errors=errors,
        )
    except (OSError, sqlite3.Error, ValueError, TemplateError) as error:
        logger.error("PI browser generation failed: %s", error)
        errors.print(f"Error: {error}", markup=False, soft_wrap=True)
        raise typer.Exit(code=1) from error


def _collect_inputs(settings: EveArgusSettings) -> PiMarketInputs:
    """Select only Jita's latest regional response and one common Forge window."""
    hub = resolve_jita_hub()
    catalog = load_catalog()
    generated_at = Instant.now()
    generation_date = date.fromisoformat(generated_at.format_iso()[:10])
    if not settings.argus_dynamic_database.is_file():
        raise ValueError(
            "No stored market orders database. Fetch source orders with "
            f"'eve-argus fetch market-orders --region-id {hub.region_id}'."
        )
    with ExitStack() as stack:
        dynamic = stack.enter_context(
            db_connection_manager(settings.argus_dynamic_database, read_only=True)
        )
        responses = dynamic_read.market_orders_responses(
            dynamic, region_id=hub.region_id
        )
        if not responses:
            raise ValueError(
                "No stored The Forge market orders. Fetch source orders with "
                f"'eve-argus fetch market-orders --region-id {hub.region_id}'."
            )
        response = responses[0]
        books: dict[int, BuySellOrders] = {}
        for type_id in catalog:
            records = dynamic_read.market_orders_filtered(
                dynamic,
                response.response_metadata_id,
                type_id=type_id,
                location_id=hub.station_id,
            )
            books[type_id] = BuySellOrders(
                buy_orders=tuple(record for record in records if record.is_buy_order),
                sell_orders=tuple(
                    record for record in records if not record.is_buy_order
                ),
            )
        orders = MarketOrdersDataset(
            response_metadata_id=response.response_metadata_id,
            received_at=response.received_at,
            expires_at=response.expires_at,
            argus_expires_at=response.argus_expires_at,
            region_id=response.region_id,
            records=books,
        )
        history = None
        history_path = settings.market_history_database
        if history_path.exists() and not history_path.is_file():
            raise ValueError(f"History database path is not a file: {history_path}")
        if history_path.is_file():
            connection = stack.enter_context(
                db_connection_manager(history_path, read_only=True)
            )
            newest = history_read.newest_market_history_date(
                connection, region_id=hub.region_id, before=generation_date.isoformat()
            )
            window = (
                select_history_window(
                    newest_stored_date=newest, generation_date=generation_date
                )
                if newest is not None
                else None
            )

            def records_for(type_id: int) -> tuple[MarketHistoryRecord, ...]:
                """Read only the chosen regional calendar window for this type."""
                if window is None:
                    return ()
                return history_read.market_history_date_range(
                    connection,
                    region_id=hub.region_id,
                    type_id=type_id,
                    start=window.newest_date,
                    end=window.oldest_date,
                )

            history = RegionalHistory(window=window, records=records_for)
        return collect_pi_market_inputs(
            catalog=catalog,
            response=response,
            orders=orders,
            history=history,
            generated_at=generated_at,
        )


def _generate_browser(
    *,
    settings: EveArgusSettings,
    destination: Path,
    tax_rate: Decimal,
    intermediate_boundary: CostBoundary,
    overwrite: bool,
    messenger: Console,
    errors: Console,
) -> None:
    """Preflight every asset, collect/render, then write without touching other files."""
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"Report destination is not a directory: {destination}")
    for name in BROWSER_FILES:
        path = destination / name
        if path.is_symlink() or path.exists() and (not overwrite or not path.is_file()):
            raise ValueError(
                f"Browser output path already exists or is unsafe: {path}. "
                "Use --overwrite for existing regular generated files."
            )
    messenger.print(
        "Collecting stored Jita prices and The Forge history...", markup=False
    )
    inputs = _collect_inputs(settings)
    for warning in inputs.warnings:
        errors.print(f"Warning: {warning}", markup=False, soft_wrap=True)
    outputs = render_pi_browser(
        inputs, tax_rate=tax_rate, intermediate_boundary=intermediate_boundary
    )
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        with (destination / name).open(
            "w" if overwrite else "x", encoding="utf-8", newline=""
        ) as stream:
            stream.write(content)
    messenger.print(f"Open {(destination / 'index.html').resolve()}", markup=False)
