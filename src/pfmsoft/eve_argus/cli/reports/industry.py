"""Generate production estimates from stored industry and market snapshots."""

import logging
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer
from jinja2 import TemplateError
from rich.console import Console

from pfmsoft.eve_argus.cli.helpers import (
    get_eve_argus_settings_from_context,
    get_static_database_path,
)
from pfmsoft.eve_argus.cli.reports._industry_inputs import DatabasePaths, read_inputs
from pfmsoft.eve_argus.helpers.file_safe_string import file_safe_string
from pfmsoft.eve_argus.reports.industry import Planner, build_report
from pfmsoft.eve_argus.reports.industry_render import write_reports

logger = logging.getLogger(__name__)
app = typer.Typer(no_args_is_help=True)


@app.command(name="industry")
def industry(
    ctx: typer.Context,
    to: Annotated[Path, typer.Option("--to", help="Parent directory for the report.")],
    system_id: Annotated[
        int, typer.Option("--system-id", min=1, help="Industry solar system ID.")
    ],
    corporation_id: Annotated[
        int | None,
        typer.Option(
            "--corporation-id", min=1, help="Corporation ID or configured default."
        ),
    ] = None,
    sales_tax: Annotated[
        float, typer.Option("--sales-tax", min=0, max=100, help="Sales tax percent.")
    ] = 3.6,
    broker_fee: Annotated[
        float, typer.Option("--broker-fee", min=0, max=100, help="Broker fee percent.")
    ] = 1.0,
    owned: Annotated[
        bool, typer.Option("--owned", help="Select owned BPO products.")
    ] = False,
    not_owned: Annotated[
        bool,
        typer.Option("--not-owned", help="Select hypothetical unowned BPO products."),
    ] = False,
    sample: Annotated[
        bool, typer.Option("--sample", help="Select representative owned products.")
    ] = False,
    type_id: Annotated[
        list[int] | None, typer.Option("--type-id", help="Product type ID; repeat.")
    ] = None,
    me: Annotated[
        int, typer.Option("--me", min=0, max=10, help="Hypothetical BPO ME.")
    ] = 10,
    te: Annotated[
        int, typer.Option("--te", min=0, max=20, help="Hypothetical BPO TE.")
    ] = 20,
    history_stale: Annotated[
        int,
        typer.Option(
            "--history-stale", min=0, help="History receipt age threshold in days."
        ),
    ] = 7,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace existing report files.")
    ] = False,
    quiet: Annotated[
        bool, typer.Option("--quiet", help="Suppress progress, not warnings or errors.")
    ] = False,
) -> None:
    """Estimate BPC-based production and sale outcomes without fetching data."""
    if sum((owned, not_owned, sample, bool(type_id))) > 1:
        raise typer.BadParameter(
            "Choose only one of --owned, --not-owned, --sample, or --type-id."
        )
    if any(value <= 0 for value in type_id or ()):
        raise typer.BadParameter(
            "Product type IDs must be positive.", param_hint="--type-id"
        )
    rates = (Decimal(str(sales_tax)), Decimal(str(broker_fee)))
    if any(not rate.is_finite() or not 0 <= rate <= 100 for rate in rates):
        raise typer.BadParameter(
            "Sale fee percentages must be finite and between 0 and 100."
        )
    settings = get_eve_argus_settings_from_context(ctx)
    resolved_id = settings.corporation_id if corporation_id is None else corporation_id
    if resolved_id is None or resolved_id <= 0:
        raise typer.BadParameter(
            "Provide --corporation-id or configure default_ids.corporation_id."
        )
    errors = Console(stderr=True)
    messenger = Console(stderr=True, quiet=quiet)
    generated_at = datetime.now(UTC)
    timestamp = file_safe_string(generated_at.isoformat())
    destination = to / f"industry-{resolved_id}-{system_id}-{timestamp}"
    try:
        messenger.print("Reading stored industry and market snapshots...", markup=False)
        data, selected = read_inputs(
            DatabasePaths(
                static=get_static_database_path(settings),
                dynamic=settings.argus_dynamic_database,
                history=settings.market_history_database,
            ),
            corporation_id=resolved_id,
            system_id=system_id,
            generated_at=generated_at,
            product_ids=tuple(type_id or ()),
            selection="owned" if owned else "not-owned" if not_owned else "sample",
            me=me,
            te=te,
            history_stale_days=history_stale,
        )
        report = build_report(
            data,
            product_ids=selected,
            sales_tax_rate=rates[0] / 100,
            broker_fee_rate=rates[1] / 100,
            generated_at=generated_at,
        )
        for warning in data.warnings:
            errors.print(f"Warning: {warning}", markup=False)
        for source in data.sources:
            if source.freshness(now=generated_at) == "stale":
                errors.print(
                    f"Warning: stale source: {source.label}, {source.received_at}",
                    markup=False,
                )
        planner = Planner(data)
        for plan in report.plans:
            for warning in plan.warnings:
                errors.print(
                    f"Warning [{planner.identity(plan.type_id)}/{plan.strategy}]: {warning}",
                    markup=False,
                )
        paths = write_reports(report, destination=destination, overwrite=overwrite)
    except (OSError, sqlite3.Error, ValueError, TemplateError) as error:
        logger.error("Industry report failed: %s", error)
        errors.print(f"Error: {error}", markup=False, soft_wrap=True)
        raise typer.Exit(code=1) from error
    messenger.print(
        f"Wrote {len(paths)} files to {destination.resolve()}", markup=False
    )
