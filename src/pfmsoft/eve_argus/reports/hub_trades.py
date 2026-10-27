"""Collect live hub-to-hub trades from stored primary-station order snapshots.

A hub trade buys from sell orders at one hub's primary station, hauls the items,
and sells them immediately into buy orders at another hub's primary station. No
orders are placed, so no broker fees apply; sales tax and an ISK-per-m³ transport
rate are deducted.

Quantities come from walking both books: the cheapest source sells are matched
against the highest destination buys while each unit remains profitable. Each
destination's walk is independent, so profits to different destinations for the
same item compete for the same supply and must not be added together.

Collectors are pure: callers supply validated station books and static datasets.
"""

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Literal

from whenever import Instant

from pfmsoft.eve_argus.dynamic.models import (
    MarketOrderRecord,
    MarketOrdersDataset,
    MarketOrdersResponse,
)
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS, MarketHub
from pfmsoft.eve_argus.reports.station_trades import (
    OrdersFreshness,
    active_station_book,
    is_selected_market_path,
    order_snapshot_freshness,
    station_market_path,
    validate_market_group_ids,
    validate_order_snapshot,
)
from pfmsoft.eve_argus.static.models import (
    MarketGroupsDataset,
    TypesDataset,
    TypesRecord,
)

SCHEMA_VERSION: Literal[1] = 1
MAX_SNAPSHOT_SPREAD_SECONDS = 30 * 60
"""Warn when the order snapshots were received further apart than this."""
REPORT_WIDE_FLAGS = frozenset(
    {
        "incomplete_competition_coverage",
        "zero_sales_tax",
        "zero_transport_rate",
        "snapshot_age_gap",
        "expired_source_orders",
        "unknown_source_expiry",
    }
)
"""Flags that apply to every row of a report and are shown once as notices."""

type Status = Literal["ranked", "below_min_profit", "unknown_volume"]
type LimitReason = Literal["profit_exhausted", "source_supply", "destination_demand"]
type StationBook = tuple[tuple[MarketOrderRecord, ...], tuple[MarketOrderRecord, ...]]
"""Active station buy orders and sell orders for one type."""


@dataclass(slots=True, kw_only=True, frozen=True)
class HubTradesOptions:
    """Validated cost settings and market-group filters for one run."""

    sales_tax_percent: Decimal = Decimal(0)
    """Sales tax percent of gross revenue from destination buy orders."""
    transport_per_m3: Decimal = Decimal(0)
    """Transport cost in ISK per m³ hauled."""
    min_profit: Decimal = Decimal(0)
    """Rows must have total net profit above this ISK amount to rank."""
    include_market_group_ids: tuple[int, ...] = ()
    """Market-group subtrees to include; empty includes all."""
    exclude_market_group_ids: tuple[int, ...] = ()
    """Market-group subtrees to exclude; exclusions win."""

    def __post_init__(self) -> None:
        """Validate numeric settings.

        Raises:
            ValueError: If a value is out of range or not finite.
        """
        if (
            not self.sales_tax_percent.is_finite()
            or not 0 <= self.sales_tax_percent <= 100
        ):
            raise ValueError(
                f"sales_tax_percent must be between 0 and 100, "
                f"got {self.sales_tax_percent}."
            )
        for name in ("transport_per_m3", "min_profit"):
            value: Decimal = getattr(self, name)
            if not value.is_finite() or value < 0:
                raise ValueError(f"{name} must be non-negative, got {value}.")


@dataclass(slots=True, kw_only=True, frozen=True)
class HubStationBooks:
    """One hub's validated order snapshot reduced to active station books."""

    hub: MarketHub
    response: MarketOrdersResponse
    books: dict[int, StationBook]
    """Active station (buys, sells) keyed by type ID; empty books are omitted."""


@dataclass(slots=True, kw_only=True, frozen=True)
class SnapshotProvenance:
    """Identity and freshness of one hub's order snapshot."""

    hub: MarketHub
    response_metadata_id: int
    received_at: str
    expires_at: str | None
    argus_expires_at: str | None
    expiry_used: str | None
    freshness: OrdersFreshness


@dataclass(slots=True, kw_only=True, frozen=True)
class Fill:
    """One matched quantity between a source sell and a destination buy order."""

    source_order_id: int
    destination_order_id: int
    quantity: int
    sell_price: Decimal
    buy_price: Decimal
    net_profit_per_unit: Decimal


@dataclass(slots=True, kw_only=True, frozen=True)
class WalkResult:
    """The fills from walking both books and why the walk stopped."""

    fills: tuple[Fill, ...]
    limit_reason: LimitReason
    min_volume_skipped: bool


@dataclass(slots=True, kw_only=True, frozen=True)
class TradeTotals:
    """Totals over a walk's fills."""

    units: int
    total_m3: Decimal | None
    purchase_cost: Decimal
    gross_revenue: Decimal
    sales_tax: Decimal
    transport_cost: Decimal
    net_profit: Decimal
    net_margin_percent: Decimal
    profit_per_m3: Decimal | None
    last_sell_price: Decimal
    average_sell_price: Decimal
    last_buy_price: Decimal
    average_buy_price: Decimal
    source_order_count: int
    destination_order_count: int


@dataclass(slots=True, kw_only=True, frozen=True)
class HubTradeRow:
    """One source-to-destination candidate for one type."""

    destination_station_id: int
    destination_system_name: str
    type_id: int
    type_name: str
    market_group_id: int
    market_path_names: tuple[str, ...]
    status: Status
    rank: int | None
    flags: tuple[str, ...]
    m3_per_unit: Decimal | None
    best_sell_price: Decimal
    best_buy_price: Decimal
    source_available_units: int
    destination_demand_units: int
    limit_reason: LimitReason | None
    totals: TradeTotals | None
    """None when the row was not walked (unknown volume)."""
    fills: tuple[Fill, ...]
    destination_match_count: int
    is_best_match: bool
    best_match_destination: str | None
    alternate_destinations: tuple[str, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class MultiDestinationItem:
    """An item profitable to two or more destinations from one source."""

    best: HubTradeRow
    alternates: tuple[HubTradeRow, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class HubTradesReport:
    """One source station's trades to every other hub's primary station."""

    schema_version: Literal[1]
    generated_at: str
    source: SnapshotProvenance
    destinations: tuple[SnapshotProvenance, ...]
    snapshot_spread_seconds: int
    """Seconds between the oldest and newest order snapshot received."""
    options: HubTradesOptions
    filtered_out_count: int
    """Candidate types removed by the market-group filters."""
    no_overlap_count: int
    """Dropped source/destination/type candidates with no profitable unit."""
    warnings: tuple[str, ...]
    records: tuple[HubTradeRow, ...]

    @property
    def ranked(self) -> tuple[HubTradeRow, ...]:
        """Return ranked rows in rank order."""
        return tuple(row for row in self.records if row.status == "ranked")

    @property
    def status_counts(self) -> dict[str, int]:
        """Return kept rows per status, plus dropped no-overlap candidates."""
        counts = Counter[str](row.status for row in self.records)
        counts["no_overlap"] = self.no_overlap_count
        return dict(sorted(counts.items()))

    @property
    def best_matches(self) -> tuple[HubTradeRow, ...]:
        """Return each ranked item's best destination row, in rank order."""
        return tuple(row for row in self.ranked if row.is_best_match)

    @property
    def multi_destination_items(self) -> tuple[MultiDestinationItem, ...]:
        """Return items with several ranked destinations, by best-match rank."""
        alternates: dict[int, list[HubTradeRow]] = defaultdict(list)
        for row in self.ranked:
            if not row.is_best_match:
                alternates[row.type_id].append(row)
        return tuple(
            MultiDestinationItem(best=row, alternates=tuple(alternates[row.type_id]))
            for row in self.best_matches
            if row.destination_match_count > 1
        )


def unit_volume_m3(record: TypesRecord) -> Decimal | None:
    """Return hauled m³ per unit, preferring packaged volume.

    Returns:
        The packaged volume, else the volume, or None when neither is positive.
    """
    for value in (record.packaged_volume, record.volume):
        if value:
            return Decimal(str(value))
    return None


def build_station_books(
    *, hub: MarketHub, response: MarketOrdersResponse, orders: MarketOrdersDataset
) -> HubStationBooks:
    """Validate one hub snapshot and keep its active primary-station books.

    Raises:
        ValueError: If the snapshot or any order is inconsistent.
    """
    validate_order_snapshot(hub=hub, response=response, orders=orders)
    books: dict[int, StationBook] = {}
    for type_id, book in orders.records.items():
        buys, sells = active_station_book(
            hub=hub,
            type_id=type_id,
            book=book,
            response_metadata_id=response.response_metadata_id,
        )
        if buys or sells:
            books[type_id] = (buys, sells)
    return HubStationBooks(hub=hub, response=response, books=books)


def _profit_per_unit(
    *, sell: Decimal, buy: Decimal, tax_factor: Decimal, transport: Decimal
) -> Decimal:
    return buy * tax_factor - sell - transport


def walk_books(
    *,
    sells: Iterable[MarketOrderRecord],
    buys: Iterable[MarketOrderRecord],
    m3_per_unit: Decimal | None,
    options: HubTradesOptions,
) -> WalkResult:
    """Match cheapest source sells to highest destination buys while profitable.

    A buy order is skipped when the profitable supply still available cannot meet
    its minimum volume (or its remaining volume, if smaller).

    Args:
        sells: Active source sell orders.
        buys: Active destination buy orders.
        m3_per_unit: Hauled volume per unit; None is treated as 0 m³.
        options: Sales tax and transport settings.

    Returns:
        The fills in walk order, the stop reason, and whether a buy was skipped.
    """
    sell_orders = sorted(sells, key=lambda order: (order.price, order.order_id))
    buy_orders = sorted(buys, key=lambda order: (-order.price, order.order_id))
    sell_left = [order.volume_remain for order in sell_orders]
    buy_left = [order.volume_remain for order in buy_orders]
    tax_factor = 1 - options.sales_tax_percent / 100
    transport = options.transport_per_m3 * (m3_per_unit or 0)
    fills: list[Fill] = []
    skipped = False
    i = j = 0
    while True:
        if i >= len(sell_orders):
            return WalkResult(
                fills=tuple(fills),
                limit_reason="source_supply",
                min_volume_skipped=skipped,
            )
        if j >= len(buy_orders):
            return WalkResult(
                fills=tuple(fills),
                limit_reason="destination_demand",
                min_volume_skipped=skipped,
            )
        sell, buy = sell_orders[i], buy_orders[j]
        profit = _profit_per_unit(
            sell=sell.price, buy=buy.price, tax_factor=tax_factor, transport=transport
        )
        if profit <= 0:
            return WalkResult(
                fills=tuple(fills),
                limit_reason="profit_exhausted",
                min_volume_skipped=skipped,
            )
        if buy_left[j] == buy.volume_remain:
            profitable_supply = sell_left[i] + sum(
                sell_left[k]
                for k in range(i + 1, len(sell_orders))
                if _profit_per_unit(
                    sell=sell_orders[k].price,
                    buy=buy.price,
                    tax_factor=tax_factor,
                    transport=transport,
                )
                > 0
            )
            if profitable_supply < min(buy.min_volume, buy.volume_remain):
                skipped = True
                j += 1
                continue
        quantity = min(sell_left[i], buy_left[j])
        fills.append(
            Fill(
                source_order_id=sell.order_id,
                destination_order_id=buy.order_id,
                quantity=quantity,
                sell_price=sell.price,
                buy_price=buy.price,
                net_profit_per_unit=profit,
            )
        )
        sell_left[i] -= quantity
        buy_left[j] -= quantity
        if not sell_left[i]:
            i += 1
        if not buy_left[j]:
            j += 1


def trade_totals(
    *, fills: Sequence[Fill], m3_per_unit: Decimal | None, options: HubTradesOptions
) -> TradeTotals:
    """Total a nonempty walk's cost, revenue, tax, transport, and profit.

    Raises:
        ValueError: If there are no fills.
    """
    if not fills:
        raise ValueError("Trade totals need at least one fill.")
    units = sum(fill.quantity for fill in fills)
    purchase = sum((fill.quantity * fill.sell_price for fill in fills), Decimal(0))
    revenue = sum((fill.quantity * fill.buy_price for fill in fills), Decimal(0))
    tax = revenue * options.sales_tax_percent / 100
    total_m3 = None if m3_per_unit is None else units * m3_per_unit
    transport = (total_m3 or Decimal(0)) * options.transport_per_m3
    net = revenue - tax - purchase - transport
    return TradeTotals(
        units=units,
        total_m3=total_m3,
        purchase_cost=purchase,
        gross_revenue=revenue,
        sales_tax=tax,
        transport_cost=transport,
        net_profit=net,
        net_margin_percent=net / purchase * 100,
        profit_per_m3=net / total_m3 if total_m3 else None,
        last_sell_price=fills[-1].sell_price,
        average_sell_price=purchase / units,
        last_buy_price=fills[-1].buy_price,
        average_buy_price=revenue / units,
        source_order_count=len({fill.source_order_id for fill in fills}),
        destination_order_count=len({fill.destination_order_id for fill in fills}),
    )


def _provenance(books: HubStationBooks, generated_at: Instant) -> SnapshotProvenance:
    expiry, freshness = order_snapshot_freshness(books.response, generated_at)
    return SnapshotProvenance(
        hub=books.hub,
        response_metadata_id=books.response.response_metadata_id,
        received_at=books.response.received_at,
        expires_at=books.response.expires_at,
        argus_expires_at=books.response.argus_expires_at,
        expiry_used=expiry,
        freshness=freshness,
    )


def _snapshot_spread_seconds(snapshots: Iterable[SnapshotProvenance]) -> int:
    received = [Instant.parse_iso(snapshot.received_at) for snapshot in snapshots]
    return int((max(received) - min(received)).total("seconds"))


def _hub_order(system_name: str) -> int:
    for index, hub in enumerate(MARKET_HUBS):
        if hub.system_name == system_name:
            return index
    return len(MARKET_HUBS)


def _rank_key(row: HubTradeRow) -> tuple[Decimal, bool, Decimal, str, int, int]:
    """Sort by net profit, profit per m³ (unknown last), name, ID, then hub."""
    totals = row.totals
    if totals is None:
        raise ValueError(f"Ranked type {row.type_id} has no trade totals.")
    per_m3 = totals.profit_per_m3
    return (
        -totals.net_profit,
        per_m3 is None,
        -(per_m3 or Decimal(0)),
        row.type_name.casefold(),
        row.type_id,
        _hub_order(row.destination_system_name),
    )


def order_rows(rows: Iterable[HubTradeRow]) -> tuple[HubTradeRow, ...]:
    """Rank rows, annotate best destination matches, then append unranked rows."""
    rows = list(rows)
    ranked = sorted((row for row in rows if row.status == "ranked"), key=_rank_key)
    by_type: dict[int, list[HubTradeRow]] = defaultdict(list)
    for row in ranked:
        by_type[row.type_id].append(row)
    annotated = []
    for rank, row in enumerate(ranked, start=1):
        matches = by_type[row.type_id]
        best = matches[0]
        annotated.append(
            replace(
                row,
                rank=rank,
                destination_match_count=len(matches),
                is_best_match=row is best,
                best_match_destination=best.destination_system_name,
                alternate_destinations=tuple(
                    match.destination_system_name for match in matches[1:]
                ),
            )
        )
    remaining = sorted(
        (row for row in rows if row.status != "ranked"),
        key=lambda row: (
            row.status,
            row.type_name.casefold(),
            row.type_id,
            _hub_order(row.destination_system_name),
        ),
    )
    return (*annotated, *remaining)


def _report_flags(
    *,
    options: HubTradesOptions,
    source: SnapshotProvenance,
    spread_seconds: int,
) -> tuple[str, ...]:
    flags = ["incomplete_competition_coverage"]
    if options.sales_tax_percent == 0:
        flags.append("zero_sales_tax")
    if options.transport_per_m3 == 0:
        flags.append("zero_transport_rate")
    if spread_seconds > MAX_SNAPSHOT_SPREAD_SECONDS:
        flags.append("snapshot_age_gap")
    match source.freshness:
        case "expired":
            flags.append("expired_source_orders")
        case "unknown":
            flags.append("unknown_source_expiry")
    return tuple(flags)


def _destination_flags(destination: SnapshotProvenance) -> tuple[str, ...]:
    match destination.freshness:
        case "expired":
            return ("expired_destination_orders",)
        case "unknown":
            return ("unknown_destination_expiry",)
        case _:
            return ()


def _report_warnings(
    *,
    options: HubTradesOptions,
    source: SnapshotProvenance,
    destinations: Sequence[SnapshotProvenance],
    spread_seconds: int,
    rows: Sequence[HubTradeRow],
    excluded_without_group: int,
) -> tuple[str, ...]:
    warnings = [
        "Only orders at each hub's primary station are matched; wider-range buy "
        "orders and other stations are not modeled."
    ]
    if options.sales_tax_percent == 0:
        warnings.append("Sales tax is 0%; net profit excludes any real sales tax.")
    if options.transport_per_m3 == 0:
        warnings.append(
            "Transport rate is 0 ISK/m³; net profit excludes any hauling cost."
        )
    for snapshot in (source, *destinations):
        match snapshot.freshness:
            case "expired":
                warnings.append(
                    f"The {snapshot.hub.system_name} order snapshot has expired; "
                    "it was not refreshed."
                )
            case "unknown":
                warnings.append(
                    f"The {snapshot.hub.system_name} order snapshot has unknown expiry."
                )
    if spread_seconds > MAX_SNAPSHOT_SPREAD_SECONDS:
        warnings.append(
            f"Order snapshots were received {spread_seconds // 60} minutes apart "
            f"(more than {MAX_SNAPSHOT_SPREAD_SECONDS // 60}); matched orders may "
            "not have coexisted."
        )
    unknown_volume = sum(row.status == "unknown_volume" for row in rows)
    if unknown_volume:
        warnings.append(
            f"{unknown_volume} candidate(s) have unknown m³ and were not evaluated "
            "with a nonzero transport rate."
        )
    if excluded_without_group:
        warnings.append(
            f"Excluded {excluded_without_group} unpublished or nonmarket candidate "
            "type(s)."
        )
    return tuple(warnings)


def _route_row(
    *,
    destination: SnapshotProvenance,
    type_record: TypesRecord,
    path: tuple[int, tuple[int, ...], tuple[str, ...]],
    sells: tuple[MarketOrderRecord, ...],
    buys: tuple[MarketOrderRecord, ...],
    options: HubTradesOptions,
    report_flags: tuple[str, ...],
) -> HubTradeRow | None:
    """Walk one route for one type; None when no unit is profitable."""
    group_id, _, names = path
    m3 = unit_volume_m3(type_record)
    flags = [*report_flags, *_destination_flags(destination)]
    walk: WalkResult | None = None
    totals: TradeTotals | None = None
    status: Status
    if m3 is None:
        flags.append("unknown_volume")
    if m3 is None and options.transport_per_m3 > 0:
        status = "unknown_volume"
    else:
        walk = walk_books(sells=sells, buys=buys, m3_per_unit=m3, options=options)
        if not walk.fills:
            return None
        if walk.min_volume_skipped:
            flags.append("min_volume_skipped")
        totals = trade_totals(fills=walk.fills, m3_per_unit=m3, options=options)
        status = (
            "below_min_profit" if totals.net_profit <= options.min_profit else "ranked"
        )
    return HubTradeRow(
        destination_station_id=destination.hub.station_id,
        destination_system_name=destination.hub.system_name,
        type_id=type_record.type_id,
        type_name=type_record.name,
        market_group_id=group_id,
        market_path_names=names,
        status=status,
        rank=None,
        flags=tuple(flags),
        m3_per_unit=m3,
        best_sell_price=min(order.price for order in sells),
        best_buy_price=max(order.price for order in buys),
        source_available_units=sum(order.volume_remain for order in sells),
        destination_demand_units=sum(order.volume_remain for order in buys),
        limit_reason=None if walk is None else walk.limit_reason,
        totals=totals,
        fills=() if walk is None else walk.fills,
        destination_match_count=0,
        is_best_match=False,
        best_match_destination=None,
        alternate_destinations=(),
    )


def collect_hub_trades(
    *,
    source: HubStationBooks,
    destinations: Sequence[HubStationBooks],
    types: TypesDataset,
    market_groups: MarketGroupsDataset,
    options: HubTradesOptions,
    generated_at: Instant,
) -> HubTradesReport:
    """Collect one source station's trades to each destination station.

    Args:
        source: The source hub's station books, whose sell orders are bought.
        destinations: Other hubs' station books, whose buy orders are sold into.
        types: Static types, including unpublished types.
        market_groups: Static market groups.
        options: Cost settings and market-group filters.
        generated_at: Report generation time.

    Returns:
        The source report with ranked rows first.

    Raises:
        ValueError: If a destination repeats or is the source, a filter ID is
            unknown, or static data is inconsistent.
    """
    station_ids = [books.hub.station_id for books in (source, *destinations)]
    if len(set(station_ids)) != len(station_ids):
        raise ValueError("Destinations must be distinct and differ from the source.")
    validate_market_group_ids(
        market_groups,
        (*options.include_market_group_ids, *options.exclude_market_group_ids),
    )
    source_provenance = _provenance(source, generated_at)
    destination_provenance = tuple(
        _provenance(books, generated_at) for books in destinations
    )
    spread = _snapshot_spread_seconds((source_provenance, *destination_provenance))
    report_flags = _report_flags(
        options=options, source=source_provenance, spread_seconds=spread
    )
    rows: list[HubTradeRow] = []
    excluded_without_group = filtered_out = no_overlap = 0
    for type_id, (_, sells) in sorted(source.books.items()):
        routes = [
            (provenance, books.books[type_id][0])
            for provenance, books in zip(
                destination_provenance, destinations, strict=True
            )
            if type_id in books.books and books.books[type_id][0]
        ]
        if not sells or not routes:
            continue
        path = station_market_path(
            type_id=type_id, types=types, market_groups=market_groups
        )
        if path is None:
            excluded_without_group += 1
            continue
        if not is_selected_market_path(
            path[1],
            include=options.include_market_group_ids,
            exclude=options.exclude_market_group_ids,
        ):
            filtered_out += 1
            continue
        for provenance, buys in routes:
            row = _route_row(
                destination=provenance,
                type_record=types[type_id],
                path=path,
                sells=sells,
                buys=buys,
                options=options,
                report_flags=report_flags,
            )
            if row is None:
                no_overlap += 1
            else:
                rows.append(row)
    return HubTradesReport(
        schema_version=SCHEMA_VERSION,
        generated_at=generated_at.format_iso(),
        source=source_provenance,
        destinations=destination_provenance,
        snapshot_spread_seconds=spread,
        options=options,
        filtered_out_count=filtered_out,
        no_overlap_count=no_overlap,
        warnings=_report_warnings(
            options=options,
            source=source_provenance,
            destinations=destination_provenance,
            spread_seconds=spread,
            rows=rows,
            excluded_without_group=excluded_without_group,
        ),
        records=order_rows(rows),
    )
