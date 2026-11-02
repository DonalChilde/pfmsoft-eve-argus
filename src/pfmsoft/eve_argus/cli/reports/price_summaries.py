"""Generate selected region and system price summaries from stored orders."""

import logging
import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
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
from pfmsoft.eve_argus.dynamic.order_summary import (
    FILTER_FACTOR_DEFAULT,
    calculate_dataset_summaries,
    validate_summary_options,
)
from pfmsoft.eve_argus.helpers.connection_helpers import db_connection_manager
from pfmsoft.eve_argus.helpers.file_safe_string import file_safe_string
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS
from pfmsoft.eve_argus.reports.price_summaries import collect_price_summaries
from pfmsoft.eve_argus.reports.price_summaries_render import (
    render_price_summaries_csv,
    render_price_summaries_json,
)
from pfmsoft.eve_argus.settings import EveArgusSettings
from pfmsoft.eve_argus.static import read as static_read
from pfmsoft.eve_argus.static.models import MapRegionsDataset, MapSolarSystemsDataset

logger = logging.getLogger(__name__)
app = typer.Typer(no_args_is_help=True)


@dataclass(slots=True, kw_only=True, frozen=True)
class PriceScope:
    """A region-wide or system-specific report scope."""

    region_id: int
    region_name: str
    system_id: int | None
    system_name: str | None

    @property
    def name(self) -> str:
        """Return the text name used for the scope's output files."""
        return self.region_name if self.system_id is None else self.system_name or ""


@app.command(name="price-summaries")
def price_summaries(
    ctx: typer.Context,
    to: Annotated[
        Path,
        typer.Option("--to", help="Directory for per-scope CSV and JSON reports."),
    ],
    region_id: Annotated[
        list[int] | None,
        typer.Option("--region-id", help="Region ID; repeat to select multiple."),
    ] = None,
    system_id: Annotated[
        list[int] | None,
        typer.Option("--system-id", help="System ID; repeat to select multiple."),
    ] = None,
    hubs: Annotated[
        bool,
        typer.Option("--hubs", help="Append configured market-hub system scopes."),
    ] = False,
    filter_factor: Annotated[
        str,
        typer.Option(
            "--filter-factor",
            help="Outlier filter factor; must be finite and greater than 1.",
        ),
    ] = str(FILTER_FACTOR_DEFAULT),
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace existing report files.")
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet", help="Suppress progress, not errors or stale-data warnings."
        ),
    ] = False,
) -> None:
    """Export region- or system-scoped prices from the latest stored orders."""
    if not region_id and not system_id and not hubs:
        raise typer.BadParameter(
            "Select at least one --region-id, --system-id, or use --hubs."
        )
    try:
        factor = Decimal(filter_factor)
    except InvalidOperation as error:
        raise typer.BadParameter(
            "Filter factor must be a decimal number.", param_hint="--filter-factor"
        ) from error
    try:
        validate_summary_options(system_id=None, location_id=None, filter_factor=factor)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="--filter-factor") from error

    settings = get_eve_argus_settings_from_context(ctx)
    errors = Console(stderr=True)
    try:
        _generate_reports(
            settings=settings,
            destination=to,
            region_ids=region_id or [],
            system_ids=system_id or [],
            hubs=hubs,
            filter_factor=factor,
            overwrite=overwrite,
            messenger=Console(stderr=True, quiet=quiet),
            errors=errors,
        )
    except (OSError, sqlite3.Error, ValueError) as error:
        logger.error("Price summaries export failed: %s", error)
        errors.print(f"Error: {error}", markup=False, soft_wrap=True)
        raise typer.Exit(code=1) from error


def _resolve_scopes(
    *,
    region_ids: list[int],
    system_ids: list[int],
    hubs: bool,
    regions: MapRegionsDataset,
    systems: MapSolarSystemsDataset,
) -> list[PriceScope]:
    """Resolve and deduplicate scopes in region, system, then hub order."""
    scopes: list[PriceScope] = []
    seen: set[tuple[int, int | None]] = set()

    def add_region(selected_region_id: int) -> None:
        if selected_region_id <= 0 or selected_region_id not in regions:
            raise typer.BadParameter(
                f"Unknown or invalid region ID {selected_region_id}.",
                param_hint="--region-id",
            )
        key = (selected_region_id, None)
        if key not in seen:
            region = regions[selected_region_id]
            scopes.append(
                PriceScope(
                    region_id=selected_region_id,
                    region_name=region.name,
                    system_id=None,
                    system_name=None,
                )
            )
            seen.add(key)

    def add_system(selected_system_id: int, *, option: str) -> None:
        if selected_system_id <= 0 or selected_system_id not in systems:
            raise typer.BadParameter(
                f"Unknown or invalid system ID {selected_system_id}.",
                param_hint=option,
            )
        system = systems[selected_system_id]
        region = regions.get(system.region_id)
        if region is None:
            raise ValueError(
                f"System {system.name} ({selected_system_id}) references missing "
                f"region {system.region_id} in static data."
            )
        key = (system.region_id, selected_system_id)
        if key not in seen:
            scopes.append(
                PriceScope(
                    region_id=system.region_id,
                    region_name=region.name,
                    system_id=selected_system_id,
                    system_name=system.name,
                )
            )
            seen.add(key)

    for selected_region_id in region_ids:
        add_region(selected_region_id)
    for selected_system_id in system_ids:
        add_system(selected_system_id, option="--system-id")
    if hubs:
        for hub in MARKET_HUBS:
            system = systems.get(hub.system_id)
            if system is None:
                raise ValueError(
                    f"Configured hub system {hub.system_name} ({hub.system_id}) "
                    "is missing from static data."
                )
            if system.region_id != hub.region_id:
                raise ValueError(
                    f"Configured hub {hub.system_name} has inconsistent static "
                    "region data."
                )
            add_system(hub.system_id, option="--hubs")
    return scopes


def _preflight_outputs(
    *,
    destination: Path,
    scopes: list[PriceScope],
    responses: dict[int, MarketOrdersResponse],
    overwrite: bool,
) -> dict[tuple[int, int | None], Path]:
    """Validate all paths and return sanitized output stems keyed by scope."""
    stems: dict[tuple[int, int | None], Path] = {}
    paths: set[Path] = set()
    for scope in scopes:
        timestamp = file_safe_string(responses[scope.region_id].received_at)
        name = file_safe_string(scope.name)
        if not name or not timestamp:
            raise ValueError(
                f"Empty sanitized filename component for scope {scope.name}."
            )
        stem = destination / f"price-summary-{name}-{timestamp}"
        stems[(scope.region_id, scope.system_id)] = stem
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


def _generate_reports(
    *,
    settings: EveArgusSettings,
    destination: Path,
    region_ids: list[int],
    system_ids: list[int],
    hubs: bool,
    filter_factor: Decimal,
    overwrite: bool,
    messenger: Console,
    errors: Console,
) -> None:
    """Preflight scopes and outputs, render every report, then write the exports."""
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
        regions = static_read.map_regions(static)
        systems = static_read.map_solar_systems(static)
        scopes = _resolve_scopes(
            region_ids=region_ids,
            system_ids=system_ids,
            hubs=hubs,
            regions=regions,
            systems=systems,
        )
        region_scope_ids = list(dict.fromkeys(scope.region_id for scope in scopes))
        responses_by_region = {
            selected_region_id: dynamic_read.market_orders_responses(
                dynamic, region_id=selected_region_id
            )
            for selected_region_id in region_scope_ids
        }
        missing_region_ids = [
            selected_region_id
            for selected_region_id, responses in responses_by_region.items()
            if not responses
        ]
        if missing_region_ids:
            missing = ", ".join(
                f"{regions[region_id].name} ({region_id})"
                for region_id in missing_region_ids
            )
            fetch_hints = "; ".join(
                f"eve-argus fetch market-orders --region-id {region_id}"
                for region_id in missing_region_ids
            )
            raise ValueError(
                f"No stored regional market orders for: {missing}. "
                f"Fetch source orders with: {fetch_hints}"
            )
        responses = {
            region_id: region_responses[0]
            for region_id, region_responses in responses_by_region.items()
        }
        stems = _preflight_outputs(
            destination=destination,
            scopes=scopes,
            responses=responses,
            overwrite=overwrite,
        )
        types = static_read.types(static, only_published=False)
        market_groups = static_read.market_groups(static)
        for region_id in region_scope_ids:
            response = responses[region_id]
            orders = dynamic_read.market_orders(
                dynamic, response_metadata_id=response.response_metadata_id
            )
            for scope in (item for item in scopes if item.region_id == region_id):
                messenger.print(
                    f"Calculating {scope.name} prices from orders received "
                    f"{response.received_at}...",
                    markup=False,
                )
                summaries = calculate_dataset_summaries(
                    orders,
                    system_id=scope.system_id,
                    filter_factor=filter_factor,
                )
                report = collect_price_summaries(
                    summaries=summaries,
                    response=response,
                    region_name=scope.region_name,
                    system_name=scope.system_name,
                    types=types,
                    market_groups=market_groups,
                    generated_at=generated_at,
                    filter_factor=filter_factor,
                )
                if report.is_stale:
                    errors.print(
                        f"Warning: the stored {scope.name} order snapshot has "
                        "expired; it was not refreshed.",
                        markup=False,
                    )
                stem = stems[(scope.region_id, scope.system_id)]
                outputs[stem.with_name(stem.name + ".csv")] = (
                    render_price_summaries_csv(report)
                )
                outputs[stem.with_name(stem.name + ".json")] = (
                    render_price_summaries_json(report)
                )

    destination.mkdir(parents=True, exist_ok=True)
    for path, content in outputs.items():
        with path.open(
            "w" if overwrite else "x", encoding="utf-8", newline=""
        ) as stream:
            stream.write(content)
        messenger.print(f"Wrote {path}", markup=False)
