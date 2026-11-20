"""Generate the standalone planetary operations HTML report."""

import logging
import sqlite3
from contextlib import ExitStack
from pathlib import Path
from typing import Annotated

import typer
from jinja2 import TemplateError
from rich.console import Console
from whenever import Instant

from pfmsoft.eve_argus.cli.helpers import (
    get_eve_argus_settings_from_context,
    get_static_database_path,
)
from pfmsoft.eve_argus.cli.reports.history_summary import _history_inputs
from pfmsoft.eve_argus.dynamic import read as dynamic_read
from pfmsoft.eve_argus.dynamic.models import BuySellOrders, MarketOrdersDataset
from pfmsoft.eve_argus.dynamic.order_summary import calculate_dataset_summaries
from pfmsoft.eve_argus.helpers.connection_helpers import db_connection_manager
from pfmsoft.eve_argus.pi.catalog import load_catalog
from pfmsoft.eve_argus.reports.history_summary import (
    HistorySummaryInput,
    collect_history_summary_report,
)
from pfmsoft.eve_argus.reports.pi_market_inputs import resolve_jita_hub
from pfmsoft.eve_argus.reports.pi_operations import (
    PiOperationsReport,
    render_pi_operations,
)
from pfmsoft.eve_argus.reports.price_summaries import collect_price_summaries
from pfmsoft.eve_argus.settings import EveArgusSettings
from pfmsoft.eve_argus.static import read as static_read

logger = logging.getLogger(__name__)
app = typer.Typer(no_args_is_help=True)


def _collect_report(settings: EveArgusSettings) -> PiOperationsReport:
    """Select the latest stored Forge orders and per-type history windows."""
    hub = resolve_jita_hub()
    catalog = load_catalog()
    generated_at = Instant.now()
    fetch_orders = f"Fetch source orders with 'eve-argus fetch market-orders --region-id {hub.region_id}'."
    if not settings.argus_dynamic_database.exists():
        raise ValueError(f"No stored market orders database. {fetch_orders}")
    with ExitStack() as stack:
        dynamic = stack.enter_context(
            db_connection_manager(settings.argus_dynamic_database, read_only=True)
        )
        responses = dynamic_read.market_orders_responses(
            dynamic, region_id=hub.region_id
        )
        if not responses:
            raise ValueError(
                f"No stored {hub.region_name} market orders. {fetch_orders}"
            )
        response = responses[0]
        books = {}
        for type_id in catalog:
            rows = dynamic_read.market_orders_filtered(
                dynamic, response.response_metadata_id, type_id=type_id
            )
            books[type_id] = BuySellOrders(
                buy_orders=tuple(row for row in rows if row.is_buy_order),
                sell_orders=tuple(row for row in rows if not row.is_buy_order),
            )
        orders = MarketOrdersDataset(
            response_metadata_id=response.response_metadata_id,
            received_at=response.received_at,
            expires_at=response.expires_at,
            argus_expires_at=response.argus_expires_at,
            region_id=response.region_id,
            records=books,
        )
        static = stack.enter_context(
            db_connection_manager(get_static_database_path(settings), read_only=True)
        )
        types = static_read.types(static, only_published=False)
        groups = static_read.market_groups(static)
        jita, forge = (
            collect_price_summaries(
                summaries=calculate_dataset_summaries(orders, system_id=system_id),
                response=response,
                region_name=hub.region_name,
                system_name=system_name,
                types=types,
                market_groups=groups,
                generated_at=generated_at,
            )
            for system_id, system_name in (
                (hub.system_id, hub.system_name),
                (None, None),
            )
        )
        history_path = settings.market_history_database
        if history_path.exists():
            history = stack.enter_context(
                db_connection_manager(history_path, read_only=True)
            )
            history_inputs = _history_inputs(
                connection=history,
                region_id=hub.region_id,
                type_ids=tuple(catalog),
                period_days=10,
                start_date=None,
            )
        else:
            history_inputs = tuple(
                HistorySummaryInput(
                    type_id=type_id, dates=(), records=(), latest_record=None
                )
                for type_id in catalog
            )
        return PiOperationsReport(
            materials=tuple(catalog.values()),
            jita=jita,
            forge=forge,
            history=collect_history_summary_report(
                region_id=hub.region_id,
                region_name=hub.region_name,
                period_days=10,
                start_date=None,
                summaries=history_inputs,
                types=types,
                market_groups=groups,
                generated_at=generated_at,
            ),
        )


@app.command(name="planetary-operations")
def planetary_operations(
    ctx: typer.Context,
    to: Annotated[
        Path, typer.Option("--to", help="Path for the standalone HTML file.")
    ],
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace the existing file.")
    ] = False,
    quiet: Annotated[
        bool, typer.Option("--quiet", help="Suppress progress, not warnings or errors.")
    ] = False,
) -> None:
    """Generate an offline PI operations report without refreshing market data."""
    errors = Console(stderr=True)
    messenger = Console(stderr=True, quiet=quiet)
    try:
        if to.is_symlink() or to.exists() and (not to.is_file() or not overwrite):
            raise ValueError(
                f"Output path exists or is unsafe: {to}. Use --overwrite for regular files."
            )
        if to.suffix.lower() != ".html":
            raise ValueError("The output path must end in .html.")
        for parent in to.parents:
            if parent.exists() and not parent.is_dir():
                raise ValueError(f"Output parent is not a directory: {parent}")
        messenger.print(
            "Reading stored Jita and The Forge market data...", markup=False
        )
        report = _collect_report(get_eve_argus_settings_from_context(ctx))
        if report.jita.is_stale:
            errors.print(
                f"Warning: The Forge order snapshot received {report.jita.received_at} is stale.",
                markup=False,
            )
        history = report.history
        if not any(row.average_price is not None for row in history.records):
            errors.print(
                "Warning: No priced The Forge history is available for PI materials. "
                f"Fetch source history with 'eve-argus fetch market-history --region-id {history.region_id} --market-types'.",
                markup=False,
            )
        if any(row.is_stale for row in history.records):
            errors.print(
                "Warning: Some The Forge market history is stale.", markup=False
            )
        output = render_pi_operations(report)
        to.parent.mkdir(parents=True, exist_ok=True)
        with to.open("w" if overwrite else "x", encoding="utf-8", newline="") as stream:
            stream.write(output)
    except (OSError, sqlite3.Error, ValueError, TemplateError) as error:
        logger.error("PI operations generation failed: %s", error)
        errors.print(f"Error: {error}", markup=False, soft_wrap=True)
        raise typer.Exit(code=1) from error
    messenger.print(f"Open {to.resolve()}", markup=False)
