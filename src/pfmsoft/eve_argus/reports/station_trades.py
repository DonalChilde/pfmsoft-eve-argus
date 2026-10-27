"""Collect per-station trading opportunities from stored orders and history.

Station trading places a buy order one market tick above a hub primary station's
best buy price, then relists filled items one tick below its best sell price. Rows
are ranked by an estimated daily net profit: a configurable share of regional
average daily traded volume times net profit per unit after proportional fees.

Regional history is not station volume and the daily estimate is a scenario, not
a fill forecast. Buy-order competition is limited to orders anchored at the
station; wider-range buy orders are not modeled.

Collectors are pure: callers supply datasets, a history window, and a history
records lookup.
"""

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Literal

from whenever import Instant

from pfmsoft.eve_argus.dynamic.models import (
    BuySellOrders,
    MarketOrderRecord,
    MarketOrdersDataset,
    MarketOrdersResponse,
    OrderSummaryRecord,
)
from pfmsoft.eve_argus.dynamic.order_summary import calculate_dataset_summaries
from pfmsoft.eve_argus.market_history.history_summary import (
    calculate_history_summary,
    date_range_days,
)
from pfmsoft.eve_argus.market_history.models import MarketHistoryRecord
from pfmsoft.eve_argus.models.market_hubs import MarketHub
from pfmsoft.eve_argus.static.models import MarketGroupsDataset, TypesDataset

SCHEMA_VERSION: Literal[1] = 1
HISTORY_DAYS = 10
"""Calendar days in the common regional history window."""
HISTORY_STALE_DAYS = 7
"""History whose newest used date is older than this many days is stale."""
MINIMUM_MARKET_TICK = Decimal("0.01")
MARKET_TICK_SIGNIFICANT_FIGURES = 4
PRICE_POLICY = "four significant figures, minimum 0.01 ISK tick"
COMPETITION_SCOPE = "station_anchored_only"
REPORT_WIDE_FLAGS = frozenset(
    {
        "incomplete_competition_coverage",
        "zero_fee_assumptions",
        "expired_orders",
        "unknown_order_expiry",
    }
)
"""Flags that apply to every row of a report and are shown once as notices."""

type Status = Literal[
    "ranked",
    "unprofitable",
    "missing_buy",
    "missing_sell",
    "missing_history",
    "zero_history_volume",
    "invalid_price_target",
]
type OrdersFreshness = Literal["current", "expired", "unknown"]
type HistoryFreshness = Literal["current", "stale", "missing"]
type HistoryRecordsLookup = Callable[[int], tuple[MarketHistoryRecord, ...]]
"""Return stored regional history records within the window for a type ID."""


@dataclass(slots=True, kw_only=True, frozen=True)
class StationTradesOptions:
    """Scenario settings. Rates and participation are percentages."""

    participation_percent: Decimal = Decimal(1)
    """Assumed share of regional daily volume completed as buy-then-sell cycles."""
    acquisition_broker_fee_percent: Decimal = Decimal(0)
    """Broker fee charged on the proposed buy order value."""
    sale_broker_fee_percent: Decimal = Decimal(0)
    """Broker fee charged on the proposed sell order value."""
    sales_tax_percent: Decimal = Decimal(0)
    """Sales tax charged on the gross sale value."""
    include_market_group_ids: tuple[int, ...] = ()
    """Market-group subtrees to include; empty includes every market group."""
    exclude_market_group_ids: tuple[int, ...] = ()
    """Market-group subtrees to exclude; exclusions win over inclusions."""

    def __post_init__(self) -> None:
        """Validate rates and participation.

        Raises:
            ValueError: If a fee is outside 0-100 or participation is outside
                (0, 100].
        """
        for name in self.fee_names():
            value = getattr(self, name)
            if not value.is_finite() or not Decimal(0) <= value <= Decimal(100):
                raise ValueError(f"{name} must be between 0 and 100, got {value}.")
        value = self.participation_percent
        if not value.is_finite() or not Decimal(0) < value <= Decimal(100):
            raise ValueError(
                f"participation_percent must be greater than 0 and at most 100, "
                f"got {value}."
            )

    @staticmethod
    def fee_names() -> tuple[str, ...]:
        """Return the names of the fee-rate fields."""
        return (
            "acquisition_broker_fee_percent",
            "sale_broker_fee_percent",
            "sales_tax_percent",
        )

    @property
    def zero_fee_names(self) -> tuple[str, ...]:
        """Return the fee-rate field names whose value is zero."""
        return tuple(name for name in self.fee_names() if getattr(self, name) == 0)


@dataclass(slots=True, kw_only=True, frozen=True)
class HistoryWindow:
    """One common consecutive calendar window for a region, newest first."""

    newest_date: str
    oldest_date: str
    dates: tuple[str, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class RegionalHistory:
    """The history window selected for a region and its records lookup.

    `window` is None when no stored date precedes the generation date.
    """

    window: HistoryWindow | None
    records: HistoryRecordsLookup


@dataclass(slots=True, kw_only=True, frozen=True)
class UnitEconomics:
    """Unrounded per-unit and optional daily-scenario economics."""

    gross_spread_per_unit: Decimal
    acquisition_broker_fee_per_unit: Decimal
    sale_broker_fee_per_unit: Decimal
    sales_tax_per_unit: Decimal
    acquisition_cost_per_unit: Decimal
    net_sale_proceeds_per_unit: Decimal
    net_profit_per_unit: Decimal
    net_margin_percent: Decimal
    estimated_daily_units: Decimal | None
    estimated_daily_net_profit: Decimal | None
    daily_acquisition_broker_fee: Decimal | None
    daily_sale_broker_fee: Decimal | None
    daily_sales_tax: Decimal | None
    modeled_acquisition_capital: Decimal | None
    modeled_sale_listing_cost: Decimal | None
    one_day_order_units: int | None
    one_day_order_acquisition_capital: Decimal | None


@dataclass(slots=True, kw_only=True, frozen=True)
class SideSummary:
    """Station-scoped 5% depth and summary metrics for one side of the book."""

    five_price: Decimal
    five_orders: int
    five_items: int
    total_items: int
    total_orders: int
    filtered_items: int
    filtered_orders: int


@dataclass(slots=True, kw_only=True, frozen=True)
class OrderContext:
    """Raw station order details retained for reviewing competition."""

    order_id: int
    price: Decimal
    volume_remain: int
    range: str
    min_volume: int


@dataclass(slots=True, kw_only=True, frozen=True)
class HistoryMetrics:
    """Regional history coverage and volume summary for one candidate type."""

    received_at: str | None
    expires_at: str | None
    argus_expires_at: str | None
    freshness: HistoryFreshness
    oldest_date_used: str | None
    newest_date_used: str | None
    missing_days: int | None
    average_price: Decimal | None
    average_daily_volume: Decimal | None
    average_daily_order_count: int | None


@dataclass(slots=True, kw_only=True, frozen=True)
class StationTradeRow:
    """One eligible (station, type) opportunity candidate."""

    type_id: int
    type_name: str
    market_group_id: int
    market_path_names: tuple[str, ...]
    status: Status
    rank: int | None
    flags: tuple[str, ...]
    missing_data: tuple[str, ...]
    best_station_buy_price: Decimal | None
    best_station_sell_price: Decimal | None
    proposed_buy_price: Decimal | None
    proposed_sell_price: Decimal | None
    proposed_buy_deviation_percent: Decimal | None
    proposed_sell_deviation_percent: Decimal | None
    five_percent_buy: SideSummary | None
    five_percent_sell: SideSummary | None
    station_buy_remaining_quantity: int
    station_sell_remaining_quantity: int
    station_buy_order_count: int
    station_sell_order_count: int
    station_buy_orders: tuple[OrderContext, ...]
    station_sell_orders: tuple[OrderContext, ...]
    history: HistoryMetrics
    economics: UnitEconomics | None


@dataclass(slots=True, kw_only=True, frozen=True)
class StationTradesReport:
    """One primary-station report with its source provenance and candidates."""

    schema_version: Literal[1]
    hub: MarketHub
    generated_at: str
    order_response_metadata_id: int
    orders_received_at: str
    orders_expires_at: str | None
    orders_argus_expires_at: str | None
    orders_expiry_used: str | None
    orders_freshness: OrdersFreshness
    history_window: HistoryWindow | None
    options: StationTradesOptions
    filtered_out_count: int
    """Station candidates removed by the market-group include/exclude filters."""
    warnings: tuple[str, ...]
    records: tuple[StationTradeRow, ...]

    @property
    def ranked(self) -> tuple[StationTradeRow, ...]:
        """Return ranked rows in rank order."""
        return tuple(row for row in self.records if row.status == "ranked")

    @property
    def status_counts(self) -> dict[str, int]:
        """Return the number of rows per status, sorted by status."""
        return dict(sorted(Counter(row.status for row in self.records).items()))


def market_tick(price: Decimal) -> Decimal:
    """Return the four-significant-figure tick for a price, minimum 0.01 ISK.

    Raises:
        ValueError: If the price is not finite and positive.
    """
    if not price.is_finite() or price <= 0:
        raise ValueError("Market tick price must be finite and positive.")
    return max(
        MINIMUM_MARKET_TICK,
        Decimal(1).scaleb(price.adjusted() - (MARKET_TICK_SIGNIFICANT_FIGURES - 1)),
    )


def next_higher_price(price: Decimal) -> Decimal:
    """Return the next valid market price strictly above a reference price."""
    tick = market_tick(price)
    ticks = (price / tick).to_integral_value(rounding=ROUND_FLOOR) + 1
    return ticks * tick


def next_lower_price(price: Decimal) -> Decimal | None:
    """Return the next valid positive market price strictly below a reference.

    Below a power of ten the price band is one digit finer, so the tick shrinks.

    Returns:
        The lower price, or None if no positive valid price is lower.
    """
    exponent = price.adjusted()
    tick = market_tick(price)
    if price == Decimal(1).scaleb(exponent):
        tick = max(
            MINIMUM_MARKET_TICK,
            Decimal(1).scaleb(exponent - MARKET_TICK_SIGNIFICANT_FIGURES),
        )
    ticks = (price / tick).to_integral_value(rounding=ROUND_CEILING) - 1
    result = ticks * tick
    return result if result > 0 else None


def proposed_price_targets(
    *, best_buy: Decimal | None, best_sell: Decimal | None
) -> tuple[Decimal | None, Decimal | None, bool]:
    """Propose a buy one tick above best buy and a sell one tick below best sell.

    Returns:
        Proposed buy, proposed sell, and whether the targets are invalid because
        no lower sell price exists or the proposed prices meet or cross.
    """
    proposed_buy = next_higher_price(best_buy) if best_buy is not None else None
    proposed_sell = next_lower_price(best_sell) if best_sell is not None else None
    invalid = (best_sell is not None and proposed_sell is None) or (
        proposed_buy is not None
        and proposed_sell is not None
        and proposed_buy >= proposed_sell
    )
    return proposed_buy, proposed_sell, invalid


def calculate_unit_economics(
    *,
    buy_price: Decimal,
    sell_price: Decimal,
    regional_daily_volume: Decimal | None,
    options: StationTradesOptions,
) -> UnitEconomics:
    """Calculate proportional fees, profit, and the daily participation scenario.

    Raises:
        ValueError: If a price is not positive or the volume is negative.
    """
    if not buy_price.is_finite() or buy_price <= 0:
        raise ValueError("Buy price must be finite and positive.")
    if not sell_price.is_finite() or sell_price <= 0:
        raise ValueError("Sell price must be finite and positive.")
    if regional_daily_volume is not None and (
        not regional_daily_volume.is_finite() or regional_daily_volume < 0
    ):
        raise ValueError("Regional daily volume must be finite and non-negative.")
    acquisition_fee = buy_price * options.acquisition_broker_fee_percent / 100
    sale_fee = sell_price * options.sale_broker_fee_percent / 100
    sales_tax = sell_price * options.sales_tax_percent / 100
    acquisition_cost = buy_price + acquisition_fee
    net_sale_proceeds = sell_price - sale_fee - sales_tax
    net_profit = net_sale_proceeds - acquisition_cost
    units = (
        None
        if regional_daily_volume is None
        else regional_daily_volume * options.participation_percent / 100
    )
    one_day_units = None if units is None else int(units)

    def daily(value: Decimal) -> Decimal | None:
        return None if units is None else units * value

    return UnitEconomics(
        gross_spread_per_unit=sell_price - buy_price,
        acquisition_broker_fee_per_unit=acquisition_fee,
        sale_broker_fee_per_unit=sale_fee,
        sales_tax_per_unit=sales_tax,
        acquisition_cost_per_unit=acquisition_cost,
        net_sale_proceeds_per_unit=net_sale_proceeds,
        net_profit_per_unit=net_profit,
        net_margin_percent=net_profit / acquisition_cost * 100,
        estimated_daily_units=units,
        estimated_daily_net_profit=daily(net_profit),
        daily_acquisition_broker_fee=daily(acquisition_fee),
        daily_sale_broker_fee=daily(sale_fee),
        daily_sales_tax=daily(sales_tax),
        modeled_acquisition_capital=daily(acquisition_cost),
        modeled_sale_listing_cost=daily(sale_fee),
        one_day_order_units=one_day_units,
        one_day_order_acquisition_capital=(
            None if one_day_units is None else one_day_units * acquisition_cost
        ),
    )


def evaluate_opportunity(
    *,
    best_buy: Decimal | None,
    best_sell: Decimal | None,
    regional_daily_volume: Decimal | None,
    options: StationTradesOptions,
) -> tuple[Status, Decimal | None, Decimal | None, UnitEconomics | None]:
    """Propose prices, calculate economics, and assign a status by precedence.

    Precedence: missing_buy, missing_sell, invalid_price_target, missing_history,
    zero_history_volume, unprofitable, then ranked.
    """
    proposed_buy, proposed_sell, invalid = proposed_price_targets(
        best_buy=best_buy, best_sell=best_sell
    )
    if best_buy is None:
        return "missing_buy", proposed_buy, proposed_sell, None
    if best_sell is None:
        return "missing_sell", proposed_buy, proposed_sell, None
    economics = (
        None
        if proposed_buy is None or proposed_sell is None
        else calculate_unit_economics(
            buy_price=proposed_buy,
            sell_price=proposed_sell,
            regional_daily_volume=regional_daily_volume,
            options=options,
        )
    )
    status: Status
    match (invalid, regional_daily_volume, economics):
        case (True, _, _):
            status = "invalid_price_target"
        case (_, None, _):
            status = "missing_history"
        case (_, volume, _) if volume == 0:
            status = "zero_history_volume"
        case (_, _, None):
            raise ValueError("Valid two-sided books must have calculable targets.")
        case (_, _, calculated) if calculated.net_profit_per_unit <= 0:
            status = "unprofitable"
        case _:
            status = "ranked"
    return status, proposed_buy, proposed_sell, economics


def select_history_window(
    *, newest_stored_date: str, generation_date: date
) -> HistoryWindow:
    """Create the common window ending on the newest stored date.

    Raises:
        ValueError: If the newest date is not strictly before the generation date.
    """
    if date.fromisoformat(newest_stored_date) >= generation_date:
        raise ValueError("History end date must be strictly before generation date.")
    dates = tuple(date_range_days(newest_stored_date, HISTORY_DAYS))
    return HistoryWindow(newest_date=dates[0], oldest_date=dates[-1], dates=dates)


def _missing_history(missing_days: int | None) -> HistoryMetrics:
    return HistoryMetrics(
        received_at=None,
        expires_at=None,
        argus_expires_at=None,
        freshness="missing",
        oldest_date_used=None,
        newest_date_used=None,
        missing_days=missing_days,
        average_price=None,
        average_daily_volume=None,
        average_daily_order_count=None,
    )


def calculate_history_metrics(
    *,
    records: tuple[MarketHistoryRecord, ...],
    region_id: int,
    type_id: int,
    window: HistoryWindow,
    generation_date: date,
) -> HistoryMetrics:
    """Summarize stored regional records over the full common calendar window.

    Absent dates count as zero volume in the daily average.

    Raises:
        ValueError: If a record has another scope or a date outside the window.
    """
    if not records:
        return _missing_history(len(window.dates))
    if any(r.region_id != region_id or r.type_id != type_id for r in records):
        raise ValueError(
            f"History scope is inconsistent for region/type {region_id}/{type_id}."
        )
    if any(record.date not in window.dates for record in records):
        raise ValueError(f"History date is outside the window for type {type_id}.")
    summary = calculate_history_summary(records=records, dates=window.dates)
    newest = max(record.date for record in records)
    age = (generation_date - date.fromisoformat(newest)).days
    return HistoryMetrics(
        received_at=summary.received_at,
        expires_at=summary.expires_at,
        argus_expires_at=summary.argus_expires_at,
        freshness="stale" if age > HISTORY_STALE_DAYS else "current",
        oldest_date_used=min(record.date for record in records),
        newest_date_used=newest,
        missing_days=summary.missing,
        average_price=summary.average if summary.volume > 0 else None,
        average_daily_volume=summary.volume,
        average_daily_order_count=summary.order_count,
    )


def validate_market_group_ids(
    market_groups: MarketGroupsDataset, group_ids: Iterable[int]
) -> None:
    """Check that every filter ID is a known market group.

    Raises:
        ValueError: If any market group ID is unknown.
    """
    unknown = sorted(set(group_ids) - market_groups.keys())
    if unknown:
        raise ValueError(f"Unknown market group IDs: {unknown}")


def is_selected_market_path(
    int_path: tuple[int, ...], *, include: Iterable[int], exclude: Iterable[int]
) -> bool:
    """Apply subtree include/exclude filters to a market path; exclusions win."""
    path = set(int_path)
    included = set(include)
    if included and path.isdisjoint(included):
        return False
    return path.isdisjoint(exclude)


def order_snapshot_freshness(
    response: MarketOrdersResponse, generated_at: Instant
) -> tuple[str | None, OrdersFreshness]:
    """Argus expiry overrides source expiry; no expiry means unknown freshness."""
    expiry = response.argus_expires_at or response.expires_at
    if expiry is None:
        return None, "unknown"
    return expiry, "expired" if Instant.parse_iso(expiry) <= generated_at else "current"


def validate_order_snapshot(
    *, hub: MarketHub, response: MarketOrdersResponse, orders: MarketOrdersDataset
) -> None:
    """Check that the response and orders describe the same regional snapshot.

    Raises:
        ValueError: If region or response metadata disagree.
    """
    if response.region_id != hub.region_id or orders.region_id != hub.region_id:
        raise ValueError(f"Order snapshot is not from the {hub.region_name} region.")
    for name in ("response_metadata_id", "received_at", "expires_at"):
        if getattr(orders, name) != getattr(response, name):
            raise ValueError(f"Order response and dataset disagree on {name}.")
    if orders.argus_expires_at != response.argus_expires_at:
        raise ValueError("Order response and dataset disagree on argus_expires_at.")
    Instant.parse_iso(response.received_at)


def active_station_book(
    *, hub: MarketHub, type_id: int, book: BuySellOrders, response_metadata_id: int
) -> tuple[tuple[MarketOrderRecord, ...], tuple[MarketOrderRecord, ...]]:
    """Validate a regional book and return active station buy and sell orders.

    Raises:
        ValueError: If an order has another provenance or scope, negative remaining
            volume, or an active nonpositive price.
    """
    for order in (*book.buy_orders, *book.sell_orders):
        if order.response_metadata_id != response_metadata_id:
            raise ValueError(f"Order {order.order_id} has inconsistent provenance.")
        if order.region_id != hub.region_id or order.type_id != type_id:
            raise ValueError(f"Order {order.order_id} has inconsistent scope.")
        if order.volume_remain < 0:
            raise ValueError(f"Order {order.order_id} has negative remaining volume.")
        if order.volume_remain > 0 and order.price <= 0:
            raise ValueError(f"Active order {order.order_id} has nonpositive price.")

    def active(orders: tuple[MarketOrderRecord, ...]) -> tuple[MarketOrderRecord, ...]:
        return tuple(
            o for o in orders if o.location_id == hub.station_id and o.volume_remain
        )

    return active(book.buy_orders), active(book.sell_orders)


def _side_summary(summary: OrderSummaryRecord | None) -> SideSummary | None:
    if summary is None:
        return None
    return SideSummary(
        five_price=summary.five_price,
        five_orders=summary.five_orders,
        five_items=summary.five_items,
        total_items=summary.total_items,
        total_orders=summary.total_orders,
        filtered_items=summary.filtered_items,
        filtered_orders=summary.filtered_orders,
    )


def _order_context(orders: tuple[MarketOrderRecord, ...]) -> tuple[OrderContext, ...]:
    return tuple(
        OrderContext(
            order_id=order.order_id,
            price=order.price,
            volume_remain=order.volume_remain,
            range=order.range,
            min_volume=order.min_volume,
        )
        for order in sorted(orders, key=lambda order: (order.price, order.order_id))
    )


def _deviation(price: Decimal | None, average: Decimal | None) -> Decimal | None:
    """Return the percent deviation of a price from a nonzero history average."""
    if price is None or average is None or average == 0:
        return None
    return (price / average - 1) * 100


def station_market_path(
    *, type_id: int, types: TypesDataset, market_groups: MarketGroupsDataset
) -> tuple[int, tuple[int, ...], tuple[str, ...]] | None:
    """Validate static identity and return the type's market-group path.

    Returns:
        Market group ID, int path, and name path; None for unpublished or
        nonmarket types.

    Raises:
        ValueError: If the type or its market group is missing or inconsistent.
    """
    record = types.get(type_id)
    if record is None or record.type_id != type_id:
        raise ValueError(
            f"Missing static type {type_id}; verify the selected static build."
        )
    if not record.published or record.market_group_id is None:
        return None
    group = market_groups.get(record.market_group_id)
    if (
        group is None
        or group.market_group_id != record.market_group_id
        or not group.int_path
        or len(group.int_path) != len(group.str_path)
        or group.int_path[-1] != group.market_group_id
    ):
        raise ValueError(
            f"Missing or invalid market group {record.market_group_id} "
            f"for type {type_id}."
        )
    return group.market_group_id, group.int_path, group.str_path


def _row_flags(
    *,
    status: Status,
    has_buy: bool,
    has_sell: bool,
    history: HistoryMetrics,
    report_flags: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return a row's quality flags and missing-data names."""
    flags = list(report_flags)
    missing: list[str] = []
    if not has_buy:
        flags.append("missing_buy")
        missing.append("station_buy_book")
    if not has_sell:
        flags.append("missing_sell")
        missing.append("station_sell_book")
    match history.freshness:
        case "missing":
            flags.append("missing_history")
            missing.append("regional_history")
        case "stale":
            flags.append("stale_history")
    if history.average_daily_volume == 0:
        flags.append("zero_history_volume")
    if status == "invalid_price_target":
        flags.append("invalid_price_target")
    return tuple(flags), tuple(missing)


def _rank_key(row: StationTradeRow) -> tuple[Decimal, Decimal, str, int]:
    """Sort by unrounded daily profit, margin, then name and ID."""
    economics = row.economics
    if economics is None or economics.estimated_daily_net_profit is None:
        raise ValueError(f"Ranked type {row.type_id} is missing ranking metrics.")
    return (
        -economics.estimated_daily_net_profit,
        -economics.net_margin_percent,
        row.type_name.casefold(),
        row.type_id,
    )


def order_rows(rows: Iterable[StationTradeRow]) -> tuple[StationTradeRow, ...]:
    """Number ranked rows first, then order the rest by status, name, and ID."""
    rows = list(rows)
    ranked = sorted((row for row in rows if row.status == "ranked"), key=_rank_key)
    remaining = sorted(
        (row for row in rows if row.status != "ranked"),
        key=lambda row: (row.status, row.type_name.casefold(), row.type_id),
    )
    return (
        *(replace(row, rank=rank) for rank, row in enumerate(ranked, start=1)),
        *(replace(row, rank=None) for row in remaining),
    )


def _report_warnings(
    *,
    options: StationTradesOptions,
    orders_freshness: OrdersFreshness,
    history: RegionalHistory | None,
    rows: list[StationTradeRow],
    excluded_without_group: int,
) -> tuple[str, ...]:
    warnings = [
        "Buy-order competition is station-anchored only; wider-range buy orders "
        "may compete but are not modeled."
    ]
    if options.zero_fee_names:
        warnings.append(
            f"Fee rates set to 0%: {', '.join(options.zero_fee_names)}; net profit "
            "excludes any real fees not entered."
        )
    match orders_freshness:
        case "expired":
            warnings.append(
                "The selected order snapshot has expired; it was not refreshed."
            )
        case "unknown":
            warnings.append("The selected order snapshot has unknown expiry.")
    if history is None:
        warnings.append(
            "Market history database is unavailable; daily estimates are unknown."
        )
    elif history.window is None:
        warnings.append("No regional history is stored before the generation date.")
    if any(row.history.freshness == "stale" for row in rows):
        warnings.append("Regional history is stale for one or more candidate types.")
    if history is not None and any(row.history.freshness == "missing" for row in rows):
        warnings.append(
            "Regional history is missing for one or more candidate types; their "
            "daily estimates are unknown and unranked."
        )
    if excluded_without_group:
        warnings.append(
            f"Excluded {excluded_without_group} unpublished or nonmarket station "
            "type(s)."
        )
    return tuple(warnings)


def collect_station_trades(
    *,
    hub: MarketHub,
    response: MarketOrdersResponse,
    orders: MarketOrdersDataset,
    types: TypesDataset,
    market_groups: MarketGroupsDataset,
    history: RegionalHistory | None,
    options: StationTradesOptions,
    generated_at: Instant,
) -> StationTradesReport:
    """Collect one hub primary station's trade candidates from explicit sources.

    Args:
        hub: The hub whose primary station is analyzed.
        response: The selected regional order response.
        orders: Orders read for that response.
        types: Static types, including unpublished types.
        market_groups: Static market groups.
        history: The region's history window and records lookup, or None when
            the history database is unavailable.
        options: Fee, participation, and market-group filter settings.
        generated_at: Report generation time.

    Returns:
        One station report with ranked rows first.

    Raises:
        ValueError: If inputs are inconsistent, a filter ID is unknown, or an
            order has invalid data.
    """
    validate_order_snapshot(hub=hub, response=response, orders=orders)
    validate_market_group_ids(
        market_groups,
        (*options.include_market_group_ids, *options.exclude_market_group_ids),
    )
    expiry, orders_freshness = order_snapshot_freshness(response, generated_at)
    generation_date = date.fromisoformat(generated_at.format_iso()[:10])
    summaries = calculate_dataset_summaries(
        _active_dataset(orders), location_id=hub.station_id
    )
    report_flags = ["incomplete_competition_coverage"]
    if options.zero_fee_names:
        report_flags.append("zero_fee_assumptions")
    match orders_freshness:
        case "expired":
            report_flags.append("expired_orders")
        case "unknown":
            report_flags.append("unknown_order_expiry")
    rows: list[StationTradeRow] = []
    excluded_without_group = filtered_out = 0
    for type_id, book in sorted(orders.records.items()):
        buys, sells = active_station_book(
            hub=hub,
            type_id=type_id,
            book=book,
            response_metadata_id=response.response_metadata_id,
        )
        if not buys and not sells:
            continue
        path = station_market_path(
            type_id=type_id, types=types, market_groups=market_groups
        )
        if path is None:
            excluded_without_group += 1
            continue
        group_id, int_path, names = path
        if not is_selected_market_path(
            int_path,
            include=options.include_market_group_ids,
            exclude=options.exclude_market_group_ids,
        ):
            filtered_out += 1
            continue
        metrics = _history_for(
            history=history,
            region_id=hub.region_id,
            type_id=type_id,
            generation_date=generation_date,
        )
        best_buy = max((order.price for order in buys), default=None)
        best_sell = min((order.price for order in sells), default=None)
        status, proposed_buy, proposed_sell, economics = evaluate_opportunity(
            best_buy=best_buy,
            best_sell=best_sell,
            regional_daily_volume=metrics.average_daily_volume,
            options=options,
        )
        flags, missing = _row_flags(
            status=status,
            has_buy=bool(buys),
            has_sell=bool(sells),
            history=metrics,
            report_flags=tuple(report_flags),
        )
        side_summaries = summaries.records.get(type_id)
        rows.append(
            StationTradeRow(
                type_id=type_id,
                type_name=types[type_id].name,
                market_group_id=group_id,
                market_path_names=names,
                status=status,
                rank=None,
                flags=flags,
                missing_data=missing,
                best_station_buy_price=best_buy,
                best_station_sell_price=best_sell,
                proposed_buy_price=proposed_buy,
                proposed_sell_price=proposed_sell,
                proposed_buy_deviation_percent=_deviation(
                    proposed_buy, metrics.average_price
                ),
                proposed_sell_deviation_percent=_deviation(
                    proposed_sell, metrics.average_price
                ),
                five_percent_buy=_side_summary(
                    side_summaries.buy_summary if side_summaries else None
                ),
                five_percent_sell=_side_summary(
                    side_summaries.sell_summary if side_summaries else None
                ),
                station_buy_remaining_quantity=sum(o.volume_remain for o in buys),
                station_sell_remaining_quantity=sum(o.volume_remain for o in sells),
                station_buy_order_count=len(buys),
                station_sell_order_count=len(sells),
                station_buy_orders=_order_context(buys),
                station_sell_orders=_order_context(sells),
                history=metrics,
                economics=economics,
            )
        )
    return StationTradesReport(
        schema_version=SCHEMA_VERSION,
        hub=hub,
        generated_at=generated_at.format_iso(),
        order_response_metadata_id=response.response_metadata_id,
        orders_received_at=response.received_at,
        orders_expires_at=response.expires_at,
        orders_argus_expires_at=response.argus_expires_at,
        orders_expiry_used=expiry,
        orders_freshness=orders_freshness,
        history_window=None if history is None else history.window,
        options=options,
        filtered_out_count=filtered_out,
        warnings=_report_warnings(
            options=options,
            orders_freshness=orders_freshness,
            history=history,
            rows=rows,
            excluded_without_group=excluded_without_group,
        ),
        records=order_rows(rows),
    )


def _active_dataset(orders: MarketOrdersDataset) -> MarketOrdersDataset:
    """Drop exhausted orders so they cannot set 5% depth summaries."""
    return replace(
        orders,
        records={
            type_id: BuySellOrders(
                buy_orders=tuple(o for o in book.buy_orders if o.volume_remain > 0),
                sell_orders=tuple(o for o in book.sell_orders if o.volume_remain > 0),
            )
            for type_id, book in orders.records.items()
        },
    )


def _history_for(
    *,
    history: RegionalHistory | None,
    region_id: int,
    type_id: int,
    generation_date: date,
) -> HistoryMetrics:
    if history is None or history.window is None:
        return _missing_history(None)
    return calculate_history_metrics(
        records=history.records(type_id),
        region_id=region_id,
        type_id=type_id,
        window=history.window,
        generation_date=generation_date,
    )
