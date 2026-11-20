"""Collect PI market price references from explicitly selected stored datasets."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from whenever import Instant

from pfmsoft.eve_argus.dynamic.models import (
    BuySellOrders,
    MarketOrdersDataset,
    MarketOrdersResponse,
)
from pfmsoft.eve_argus.dynamic.order_summary import calculate_buy_sell_summary
from pfmsoft.eve_argus.models import market_hubs
from pfmsoft.eve_argus.models.market_hubs import MarketHub
from pfmsoft.eve_argus.pi.catalog import build_catalog
from pfmsoft.eve_argus.pi.models import (
    CostBoundary,
    MarketPriceBasis,
    Material,
    SourcePrice,
)
from pfmsoft.eve_argus.reports.station_trades import (
    HistoryMetrics,
    HistoryWindow,
    OrdersFreshness,
    RegionalHistory,
    active_station_book,
    calculate_history_metrics,
    order_snapshot_freshness,
    select_history_window,
    validate_order_snapshot,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class PiMaterialPrices:
    """All market references for one catalog material, including missing quotes.

    Attributes:
        material: Canonical PI identity, tier, and recipe.
        buy: Jita primary-station buy-side 5% depth quote, before planetary import.
        sell: Jita primary-station sell-side 5% depth quote, before planetary import.
        history: Forge volume-weighted ten-day quote; unavailable at zero volume.
        history_metrics: Regional coverage, volume, and source timestamps. None
            means no regional window exists; missing type data remains explicit
            in a metrics record when a regional window does exist.
    """

    material: Material
    buy: SourcePrice
    sell: SourcePrice
    history: SourcePrice
    history_metrics: HistoryMetrics | None


@dataclass(slots=True, kw_only=True, frozen=True)
class PiMarketInputs:
    """Collected references for PI calculations and source tables.

    Attributes:
        hub: Jita entry resolved from the configured market-hub model.
        generated_at: Collection time, distinct from all source receipt times.
        response: Selected regional order response identifying the stored snapshot.
        order_expires_at: Effective order expiry, preferring Argus expiry.
        order_freshness: Current, expired, or unknown according to effective expiry.
        history_window: Common regional ten-calendar-day window, or None if absent.
        materials: Every catalog material in type-ID order, including missing prices.
        warnings: Source-level notices for callers to surface.
    """

    hub: MarketHub
    generated_at: Instant
    response: MarketOrdersResponse
    order_expires_at: str | None
    order_freshness: OrdersFreshness
    history_window: HistoryWindow | None
    materials: tuple[PiMaterialPrices, ...]
    warnings: tuple[str, ...]

    def prices_for(self, basis: MarketPriceBasis) -> dict[int, SourcePrice]:
        """Return one complete reference table, retaining unavailable quotes."""
        match basis:
            case MarketPriceBasis.JITA_BUY:
                return {row.material.type_id: row.buy for row in self.materials}
            case MarketPriceBasis.JITA_SELL:
                return {row.material.type_id: row.sell for row in self.materials}
            case MarketPriceBasis.HISTORY:
                return {row.material.type_id: row.history for row in self.materials}
            case _:
                raise ValueError(f"Unknown PI market-price basis: {basis}.")


def resolve_jita_hub() -> MarketHub:
    """Resolve the single configured Jita hub without depending on list ordering."""
    hubs = [hub for hub in market_hubs.MARKET_HUBS if hub.system_name == "Jita"]
    if len(hubs) != 1:
        raise ValueError("The market-hub model must define exactly one Jita hub.")
    return hubs[0]


def collect_pi_market_inputs(
    *,
    catalog: Mapping[int, Material],
    response: MarketOrdersResponse,
    orders: MarketOrdersDataset,
    history: RegionalHistory | None,
    generated_at: Instant,
) -> PiMarketInputs:
    """Collect station depth and regional history without I/O or source refresh.

    Callers select the latest Forge order response and the common regional
    history window. History lookups must return records within that window,
    following the existing station-trades contract. History freshness follows
    its existing newest-used-day policy; response expiry timestamps are retained.

    Raises:
        ValueError: If Jita is missing/ambiguous, snapshot provenance disagrees,
            the history window is invalid, or source records have inconsistent scope.
    """
    hub = resolve_jita_hub()
    validated = build_catalog(catalog.values())
    if any(key != material.type_id for key, material in catalog.items()):
        raise ValueError("Catalog keys must match PI material identities.")
    validate_order_snapshot(hub=hub, response=response, orders=orders)
    expiry, freshness = order_snapshot_freshness(response, generated_at)
    generation_date = date.fromisoformat(generated_at.format_iso()[:10])
    window = history.window if history is not None else None
    if window is not None and window != select_history_window(
        newest_stored_date=window.newest_date, generation_date=generation_date
    ):
        raise ValueError("PI history requires one consecutive ten-calendar-day window.")

    warnings: list[str] = []
    if freshness != "current":
        warnings.append(f"Jita order snapshot freshness is {freshness}.")
    if window is None:
        warnings.append(
            "No stored The Forge history window; history prices and volume "
            "are unavailable. Fetch with 'eve-argus fetch market-history "
            f"--region-id {hub.region_id} --type-id <type-id>'."
        )
    rows: list[PiMaterialPrices] = []
    for type_id, material in validated.items():
        book = orders.records.get(type_id, BuySellOrders(buy_orders=(), sell_orders=()))
        buy_orders, sell_orders = active_station_book(
            hub=hub,
            type_id=type_id,
            book=book,
            response_metadata_id=response.response_metadata_id,
        )
        buy_summary, sell_summary = calculate_buy_sell_summary(
            (*buy_orders, *sell_orders),
            region_id=hub.region_id,
            type_id=type_id,
            location_id=hub.station_id,
        )
        quotes: list[SourcePrice] = []
        for basis, summary in (
            (MarketPriceBasis.JITA_BUY, buy_summary),
            (MarketPriceBasis.JITA_SELL, sell_summary),
        ):
            quotes.append(
                SourcePrice(
                    source_id=(
                        f"orders:{response.response_metadata_id}:{hub.station_id}:"
                        f"{basis.value}:{type_id}"
                    ),
                    label=basis.value,
                    type_id=type_id,
                    unit_cost=summary.five_price if summary is not None else None,
                    boundary=CostBoundary.OFF_PLANET,
                    market_basis=basis,
                    unavailable_reason=(
                        f"No active {basis.value} station orders for {material.name}."
                        if summary is None
                        else None
                    ),
                )
            )
        metrics = (
            calculate_history_metrics(
                records=history.records(type_id),
                region_id=hub.region_id,
                type_id=type_id,
                window=window,
                generation_date=generation_date,
            )
            if history is not None and window is not None
            else None
        )
        reason = None
        if metrics is None or metrics.average_daily_volume is None:
            reason = f"No stored ten-day regional history for {material.name}."
        elif metrics.average_daily_volume == 0:
            reason = f"Zero traded volume in ten-day history for {material.name}."
        if metrics is not None and metrics.freshness == "stale":
            warnings.append(
                f"Stale The Forge history for {material.name}: newest used date "
                f"{metrics.newest_date_used}."
            )
        rows.append(
            PiMaterialPrices(
                material=material,
                buy=quotes[0],
                sell=quotes[1],
                history=SourcePrice(
                    source_id=(
                        f"history:{hub.region_id}:{type_id}:"
                        f"{window.newest_date if window else 'missing'}:"
                        f"{metrics.received_at if metrics else 'missing'}"
                    ),
                    label=MarketPriceBasis.HISTORY.value,
                    type_id=type_id,
                    unit_cost=metrics.average_price if metrics is not None else None,
                    boundary=CostBoundary.OFF_PLANET,
                    market_basis=MarketPriceBasis.HISTORY,
                    unavailable_reason=reason,
                ),
                history_metrics=metrics,
            )
        )
    return PiMarketInputs(
        hub=hub,
        generated_at=generated_at,
        response=response,
        order_expires_at=expiry,
        order_freshness=freshness,
        history_window=window,
        materials=tuple(rows),
        warnings=tuple(warnings),
    )
