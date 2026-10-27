"""Collect per-hub scrapmetal reprocessing deals and sourcing price points.

Deals (Scenario A) size how many units of an item can be bought now from hub-system
sell orders and reprocessed at a profit. Each item is evaluated under two material
sale scenarios: selling immediately into hub buy orders (walking the book), and
listing materials at the hub 5% sell price. Regional history summaries are optional
context for liquidity and price sanity and never set a trade price.

Price points (Scenario B) value one unit of every eligible item by its recovered
materials at each hub, giving a break-even price for sourcing the item elsewhere.

Collectors are pure: callers supply datasets, summaries, and history lookups.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import Literal, Protocol

from whenever import Instant

from pfmsoft.eve_argus.dynamic.models import (
    MarketOrderRecord,
    MarketOrdersDataset,
    MarketOrdersResponse,
    OrderSummaryDataset,
    ResponseMetadata,
)
from pfmsoft.eve_argus.market_history.models import HistorySummaryRecord
from pfmsoft.eve_argus.models.market_hubs import MarketHub
from pfmsoft.eve_argus.static.models import (
    MarketGroupsDataset,
    TypeMaterialsDataset,
    TypesDataset,
    TypesRecord,
)

SCHEMA_VERSION: Literal[1] = 1
EXCLUDED_MARKET_GROUP_IDS = frozenset({1031, 1032, 1034})
"""Raw Materials, Gas Clouds Materials, and Reaction Materials market trees."""
MAX_PORTIONS = 50_000
"""Safety cap on the number of portions bought for one item."""
HISTORY_STALE_DAYS = 7
"""History whose newest date is older than this many days is flagged stale."""
FAR_BELOW_HISTORY_PERCENT = Decimal(-30)
"""Input prices this far below the history average are flagged for checking."""
CENT = Decimal("0.01")

type Scenario = Literal["sell_to_buy_orders", "list_sell_orders"]
type DealStatus = Literal["profitable", "thin", "incomplete"]
type HistoryLookup = Callable[[int], HistorySummaryRecord | None]
"""Return the regional history summary for a type ID, or None if unavailable."""

IMMEDIATE: Scenario = "sell_to_buy_orders"
LISTING: Scenario = "list_sell_orders"
SCENARIOS: tuple[Scenario, ...] = (IMMEDIATE, LISTING)


@dataclass(slots=True, kw_only=True, frozen=True)
class ScrapmetalOptions:
    """Calculation options. All values except `min_profit` are percentages."""

    yield_percent: Decimal = Decimal(55)
    """Share of each fixed reprocessing material that is recovered."""
    reprocessing_tax: Decimal = Decimal(0)
    """Reprocessing tax as a percentage of gross material value."""
    sales_tax: Decimal = Decimal(0)
    """Sales tax as a percentage of gross material value."""
    broker_fee: Decimal = Decimal(0)
    """Listing cost as a percentage of gross material value; listings only."""
    min_profit: Decimal = Decimal(100_000)
    """Minimum total profit in ISK for a deal to be ranked."""
    min_margin: Decimal = Decimal(5)
    """Minimum margin for a portion to be bought and for a deal to be ranked."""
    max_slippage: Decimal = Decimal(10)
    """Maximum output slippage before an immediate deal is considered thin."""

    def __post_init__(self) -> None:
        """Validate rates and thresholds.

        Raises:
            ValueError: If a rate is outside 0-100 or a threshold is negative.
        """
        for name in ("yield_percent", "reprocessing_tax", "sales_tax", "broker_fee"):
            value = getattr(self, name)
            if not Decimal(0) <= value <= Decimal(100):
                raise ValueError(f"{name} must be between 0 and 100, got {value}.")
        for name in ("min_profit", "min_margin", "max_slippage"):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} must not be negative, got {value}.")

    def fees(
        self, *, scenario: Scenario, gross: Decimal
    ) -> tuple[Decimal, Decimal, Decimal]:
        """Return reprocessing tax, sales tax, and listing cost for a gross value."""
        listing = self.broker_fee if scenario == LISTING else Decimal(0)
        return (
            gross * self.reprocessing_tax / 100,
            gross * self.sales_tax / 100,
            gross * listing / 100,
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class RecoveredMaterial:
    """One material recovered from reprocessing one portion of an item."""

    type_id: int
    name: str
    quantity: int


@dataclass(slots=True, kw_only=True, frozen=True)
class ScrapmetalDealRow:
    """One hub-local buy-and-reprocess deal under one material-sale scenario.

    Money fields are None for incomplete rows. Ranked rows have a 1-based rank
    within their scenario.
    """

    scenario: Scenario
    rank: int | None
    status: DealStatus
    type_id: int
    type_name: str
    market_group_id: int | None
    market_path_names: tuple[str, ...]
    portion_size: int
    unit_volume_m3: float | None
    portions: int
    units: int
    best_price: Decimal | None
    worst_price: Decimal | None
    average_price: Decimal | None
    total_cost: Decimal | None
    gross_proceeds: Decimal | None
    reprocessing_tax: Decimal | None
    sales_tax: Decimal | None
    listing_cost: Decimal | None
    net_proceeds: Decimal | None
    profit: Decimal | None
    margin_percent: Decimal | None
    output_slippage_percent: Decimal | None
    limit_reason: str | None
    flags: tuple[str, ...]
    missing_data: tuple[str, ...]
    input_volume_m3: float | None
    materials: tuple[RecoveredMaterial, ...]
    input_history_average: Decimal | None
    input_price_vs_history_percent: Decimal | None
    input_history_daily_volume: Decimal | None
    input_history_missing_days: int | None
    input_history_newest_date: str | None
    worst_material_name: str | None
    worst_material_days_of_volume: Decimal | None


@dataclass(slots=True, kw_only=True, frozen=True)
class ScrapmetalHubReport(ResponseMetadata):
    """Deals for one hub from one regional order snapshot."""

    schema_version: Literal[1]
    region_id: int
    region_name: str
    system_id: int
    system_name: str
    generated_at: str
    is_stale: bool | None
    options: ScrapmetalOptions
    history_oldest_date: str | None
    history_newest_date: str | None
    records: tuple[ScrapmetalDealRow, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class HubPriceInputs:
    """One hub's order snapshot, system summaries, and optional history lookup."""

    hub: MarketHub
    response: MarketOrdersResponse
    summaries: OrderSummaryDataset
    history: HistoryLookup | None


@dataclass(slots=True, kw_only=True, frozen=True)
class HubPriceSource:
    """Source data used for one hub's price-point values."""

    region_id: int
    system_id: int
    system_name: str
    response_metadata_id: int
    orders_received_at: str
    is_stale: bool | None
    history_newest_date: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class HubUnitValues:
    """Gross per-unit material value of an item at one hub, by price source."""

    system_name: str
    buy: Decimal | None
    """Value at hub 5% buy prices (sell materials immediately)."""
    sell: Decimal | None
    """Value at hub 5% sell prices (list materials)."""
    history: Decimal | None
    """Value at regional history average prices (context; may lag orders)."""


@dataclass(slots=True, kw_only=True, frozen=True)
class ScrapmetalPricePointRow:
    """Per-unit reprocessed value of one item at every hub."""

    type_id: int
    type_name: str
    market_group_id: int | None
    market_path_names: tuple[str, ...]
    portion_size: int
    unit_volume_m3: float | None
    values: tuple[HubUnitValues, ...]
    best_buy_hub: str | None
    best_buy_value: Decimal | None


@dataclass(slots=True, kw_only=True, frozen=True)
class ScrapmetalPricePointsReport:
    """Per-unit break-even values for sourcing items to reprocess at a hub."""

    schema_version: Literal[1]
    generated_at: str
    yield_percent: Decimal
    hubs: tuple[HubPriceSource, ...]
    records: tuple[ScrapmetalPricePointRow, ...]


class _Pricer(Protocol):
    """Prices recovered material quantities under one sale scenario."""

    def quote(self, material_id: int, quantity: int) -> tuple[Decimal, Decimal] | None:
        """Return walked value and best-price value, or None when depth runs out."""
        ...

    def take(self, material_id: int, quantity: int) -> None:
        """Consume depth for a quoted fill."""
        ...


class _Book:
    """One side of a hub-system order book, consumed best price first."""

    def __init__(self, orders: Sequence[MarketOrderRecord]) -> None:
        """Initialize from orders already sorted best price first."""
        self.levels = [[order.price, order.volume_remain] for order in orders]
        self.total = sum(order.volume_remain for order in orders)
        self.index = 0

    def quote(self, quantity: int) -> tuple[Decimal, Decimal, Decimal] | None:
        """Price a fill without consuming it.

        Returns:
            Total value, first price, and last price; None if depth is too thin.
        """
        if quantity > self.total:
            return None
        remaining = quantity
        value = Decimal(0)
        first: Decimal | None = None
        last = Decimal(0)
        index = self.index
        while remaining > 0:
            price, volume = self.levels[index]
            index += 1
            if volume <= 0:
                continue
            take = min(volume, remaining)
            first = price if first is None else first
            last = price
            value += price * take
            remaining -= take
        assert first is not None
        return value, first, last

    def take(self, quantity: int) -> None:
        """Consume a fill that was already checked with quote."""
        remaining = quantity
        while remaining > 0:
            volume = self.levels[self.index][1]
            take = min(volume, remaining)
            self.levels[self.index][1] -= take
            remaining -= take
            self.total -= take
            if take == volume:
                self.index += 1


class _BookPricer:
    """Price materials by selling immediately into hub buy orders."""

    def __init__(
        self, buys: dict[int, tuple[MarketOrderRecord, ...]], material_ids: list[int]
    ) -> None:
        """Create one consumable buy book per material."""
        self.books = {
            material_id: _Book(buys[material_id]) for material_id in material_ids
        }

    def quote(self, material_id: int, quantity: int) -> tuple[Decimal, Decimal] | None:
        """Return walked value and best-price value, or None if depth runs out."""
        quote = self.books[material_id].quote(quantity)
        return None if quote is None else (quote[0], quote[1] * quantity)

    def take(self, material_id: int, quantity: int) -> None:
        """Consume buy-book depth."""
        self.books[material_id].take(quantity)


class _FixedPricer:
    """Price materials at a fixed listing price with no depth limit."""

    def __init__(self, prices: dict[int, Decimal]) -> None:
        """Store per-material listing prices."""
        self.prices = prices

    def quote(self, material_id: int, quantity: int) -> tuple[Decimal, Decimal]:
        """Return the listed value twice; listings have no slippage."""
        value = self.prices[material_id] * quantity
        return value, value

    def take(self, material_id: int, quantity: int) -> None:
        """Listings do not consume depth."""


@dataclass(slots=True, kw_only=True)
class _Walk:
    """Mutable accumulator for one deal while portions are bought."""

    scenario: Scenario
    record: TypesRecord
    market_path_names: tuple[str, ...]
    materials: tuple[RecoveredMaterial, ...]
    missing: tuple[str, ...]
    status: DealStatus = "profitable"
    flags: list[str] = field(default_factory=list)
    portions: int = 0
    units: int = 0
    best_price: Decimal | None = None
    worst_price: Decimal | None = None
    cost: Decimal = Decimal(0)
    gross: Decimal = Decimal(0)
    best_gross: Decimal = Decimal(0)
    reprocessing_tax: Decimal = Decimal(0)
    sales_tax: Decimal = Decimal(0)
    listing_cost: Decimal = Decimal(0)
    limit_reason: str | None = None
    material_units: dict[int, int] = field(default_factory=dict)
    history: HistorySummaryRecord | None = None
    history_vs_input: Decimal | None = None
    worst_material: tuple[str, Decimal] | None = None

    def net(self) -> Decimal:
        """Gross proceeds minus quantized fees."""
        return (
            self.gross
            - _money(self.reprocessing_tax)
            - _money(self.sales_tax)
            - _money(self.listing_cost)
        )

    def margin(self) -> Decimal | None:
        """Profit as a percentage of cost, if anything was bought."""
        return (self.net() - self.cost) / self.cost * 100 if self.cost else None

    def slippage(self) -> Decimal | None:
        """Share of best-price proceeds lost walking buy books; immediate only."""
        if self.scenario != IMMEDIATE or not self.best_gross:
            return None
        return (self.best_gross - self.gross) / self.best_gross * 100


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT)


def _optional_money(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(CENT)


def _unit_volume(record: TypesRecord) -> float | None:
    """Prefer packaged volume, which is what is hauled."""
    return record.packaged_volume if record.packaged_volume else record.volume


def _is_stale(metadata: ResponseMetadata, generated_at: Instant) -> bool | None:
    """Argus expiry overrides source expiry; no expiry means unknown freshness."""
    expiry = metadata.argus_expires_at or metadata.expires_at
    return Instant.parse_iso(expiry) <= generated_at if expiry is not None else None


def recovered_quantity(quantity: int, yield_percent: Decimal) -> int:
    """Calculate the whole units recovered from one fixed material component."""
    return int(
        (Decimal(quantity) * yield_percent / 100).to_integral_value(rounding=ROUND_DOWN)
    )


def eligible_input_ids(
    *,
    types: TypesDataset,
    type_materials: TypeMaterialsDataset,
    market_groups: MarketGroupsDataset,
) -> list[int]:
    """Select published, market-listed, non-raw-material types with fixed materials."""
    eligible: list[int] = []
    for type_id, record in sorted(types.items()):
        group = (
            market_groups.get(record.market_group_id)
            if record.market_group_id is not None
            else None
        )
        materials = type_materials.get(type_id)
        if (
            record.published
            and group is not None
            and not EXCLUDED_MARKET_GROUP_IDS.intersection(group.int_path)
            and materials is not None
            and materials.materials
        ):
            eligible.append(type_id)
    return eligible


def recovered_materials(
    *,
    type_id: int,
    types: TypesDataset,
    type_materials: TypeMaterialsDataset,
    yield_percent: Decimal,
) -> tuple[RecoveredMaterial, ...]:
    """Return materials recovered from one portion, dropping zero quantities."""
    materials: list[RecoveredMaterial] = []
    for material in type_materials[type_id].materials:
        quantity = recovered_quantity(material.quantity, yield_percent)
        if quantity <= 0:
            continue
        material_type = types.get(material.material_type_id)
        materials.append(
            RecoveredMaterial(
                type_id=material.material_type_id,
                name=material_type.name
                if material_type is not None
                else f"Unknown {material.material_type_id}",
                quantity=quantity,
            )
        )
    return tuple(materials)


def _validate_snapshot(
    *,
    hub: MarketHub,
    response: MarketOrdersResponse,
    summaries: OrderSummaryDataset,
    orders: MarketOrdersDataset | None = None,
) -> None:
    """Check that response, orders, and summaries describe the same hub snapshot.

    Raises:
        ValueError: If region, system, or response metadata disagree.
    """
    if response.region_id != hub.region_id:
        raise ValueError(f"Order response is not from the {hub.region_name} region.")
    if (
        summaries.region_id != hub.region_id
        or summaries.system_id != hub.system_id
        or summaries.location_id is not None
    ):
        raise ValueError(f"Summary dataset is not the {hub.system_name} system scope.")
    datasets: list[ResponseMetadata] = [summaries]
    if orders is not None:
        if orders.region_id != hub.region_id:
            raise ValueError(f"Order dataset is not from the {hub.region_name} region.")
        datasets.append(orders)
    for dataset in datasets:
        for name in ("response_metadata_id", "received_at", "expires_at"):
            if getattr(dataset, name) != getattr(response, name):
                raise ValueError(f"Order response and dataset disagree on {name}.")
    Instant.parse_iso(response.received_at)


def _hub_orders(
    orders: MarketOrdersDataset, system_id: int
) -> tuple[
    dict[int, tuple[MarketOrderRecord, ...]], dict[int, tuple[MarketOrderRecord, ...]]
]:
    """Split regional orders into per-type hub-system sell and buy books."""
    sells: dict[int, tuple[MarketOrderRecord, ...]] = {}
    buys: dict[int, tuple[MarketOrderRecord, ...]] = {}
    for type_id, sides in orders.records.items():
        if sell := tuple(o for o in sides.sell_orders if o.system_id == system_id):
            sells[type_id] = sell
        if buy := tuple(o for o in sides.buy_orders if o.system_id == system_id):
            buys[type_id] = buy
    return sells, buys


def _walk_portions(
    walk: _Walk,
    *,
    input_orders: Sequence[MarketOrderRecord],
    pricer: _Pricer,
    options: ScrapmetalOptions,
) -> None:
    """Buy and reprocess one portion at a time while each portion stays worthwhile."""
    input_book = _Book(input_orders)
    portion_size = walk.record.portion_size
    walk.limit_reason = "input supply exhausted"
    for _ in range(MAX_PORTIONS):
        input_quote = input_book.quote(portion_size)
        if input_quote is None:
            break
        cost, first, last = input_quote
        gross = best_gross = Decimal(0)
        blocked: str | None = None
        for material in walk.materials:
            quote = pricer.quote(material.type_id, material.quantity)
            if quote is None:
                blocked = f"{material.name} buy depth exhausted"
                break
            gross += quote[0]
            best_gross += quote[1]
        if blocked is not None:
            walk.limit_reason = blocked
            break
        fees = options.fees(scenario=walk.scenario, gross=gross)
        marginal = gross - sum(fees, Decimal(0)) - cost
        if marginal <= 0 or marginal / cost * 100 < options.min_margin:
            walk.limit_reason = "marginal portion not profitable"
            break
        input_book.take(portion_size)
        for material in walk.materials:
            pricer.take(material.type_id, material.quantity)
            walk.material_units[material.type_id] = (
                walk.material_units.get(material.type_id, 0) + material.quantity
            )
        walk.portions += 1
        walk.units += portion_size
        walk.cost += cost
        walk.gross += gross
        walk.best_gross += best_gross
        walk.reprocessing_tax += fees[0]
        walk.sales_tax += fees[1]
        walk.listing_cost += fees[2]
        walk.best_price = first if walk.best_price is None else walk.best_price
        walk.worst_price = last
    else:
        walk.limit_reason = f"capped at {MAX_PORTIONS} portions"
    slippage = walk.slippage()
    if walk.portions and slippage is not None and slippage > options.max_slippage:
        walk.status = "thin"
        walk.flags.append("high_output_slippage")


def _attach_history(walk: _Walk, *, history: HistoryLookup, generated_on: date) -> None:
    """Add price-sanity and liquidity context from regional history summaries."""
    summary = history(walk.record.type_id)
    if summary is None:
        walk.flags.append("input_history_missing")
    else:
        walk.history = summary
        if summary.average and walk.best_price is not None:
            walk.history_vs_input = (
                (walk.best_price - summary.average) / summary.average * 100
            )
            if walk.history_vs_input < FAR_BELOW_HISTORY_PERCENT:
                walk.flags.append("input_far_below_history_avg")
        if (generated_on - date.fromisoformat(summary.start)).days > HISTORY_STALE_DAYS:
            walk.flags.append("history_stale")
    for material in walk.materials:
        units = walk.material_units.get(material.type_id, 0)
        material_summary = history(material.type_id) if units else None
        if material_summary is None or not material_summary.volume:
            continue
        days = Decimal(units) / material_summary.volume
        if walk.worst_material is None or days > walk.worst_material[1]:
            walk.worst_material = (material.name, days)
    if walk.worst_material is not None and walk.worst_material[1] > 1:
        walk.flags.append("exceeds_daily_volume")
        if walk.status == "profitable":
            walk.status = "thin"


def _evaluate_input(
    *,
    record: TypesRecord,
    market_path_names: tuple[str, ...],
    materials: tuple[RecoveredMaterial, ...],
    unmarketable: set[int],
    sells: tuple[MarketOrderRecord, ...],
    buys: dict[int, tuple[MarketOrderRecord, ...]],
    listing_prices: dict[int, Decimal],
    options: ScrapmetalOptions,
) -> list[_Walk]:
    """Size a buy-and-reprocess deal for one listed input under each scenario.

    Returns:
        One walk per scenario that is incomplete or bought at least one portion.
    """
    walks: list[_Walk] = []
    for scenario in SCENARIOS:
        match scenario:
            case "sell_to_buy_orders":
                available, label = buys.keys(), "buy orders"
            case "list_sell_orders":
                available, label = listing_prices.keys(), "5% sell"
        missing = tuple(
            f"{m.name} {label}"
            for m in materials
            if m.type_id in unmarketable or m.type_id not in available
        )
        walk = _Walk(
            scenario=scenario,
            record=record,
            market_path_names=market_path_names,
            materials=materials,
            missing=missing,
        )
        if missing:
            walk.status = "incomplete"
            walk.best_price = sells[0].price
            walks.append(walk)
            continue
        pricer: _Pricer = (
            _BookPricer(buys, [m.type_id for m in materials])
            if scenario == IMMEDIATE
            else _FixedPricer(listing_prices)
        )
        _walk_portions(walk, input_orders=sells, pricer=pricer, options=options)
        if walk.portions:
            walks.append(walk)
    return walks


def _is_ranked(walk: _Walk, options: ScrapmetalOptions) -> bool:
    """Return whether a deal is actionable under the thresholds."""
    margin = walk.margin()
    return (
        walk.status == "profitable"
        and walk.net() - walk.cost >= options.min_profit
        and margin is not None
        and margin >= options.min_margin
    )


def _deal_row(walk: _Walk, *, rank: int | None) -> ScrapmetalDealRow:
    """Freeze a walk into an output row with money rounded to cents."""
    bought = walk.portions > 0
    net = walk.net()
    margin = walk.margin()
    slippage = walk.slippage()
    history = walk.history
    volume = _unit_volume(walk.record)
    return ScrapmetalDealRow(
        scenario=walk.scenario,
        rank=rank,
        status=walk.status,
        type_id=walk.record.type_id,
        type_name=walk.record.name,
        market_group_id=walk.record.market_group_id,
        market_path_names=walk.market_path_names,
        portion_size=walk.record.portion_size,
        unit_volume_m3=volume,
        portions=walk.portions,
        units=walk.units,
        best_price=walk.best_price,
        worst_price=walk.worst_price,
        average_price=_money(walk.cost / walk.units) if bought else None,
        total_cost=_money(walk.cost) if bought else None,
        gross_proceeds=_money(walk.gross) if bought else None,
        reprocessing_tax=_money(walk.reprocessing_tax) if bought else None,
        sales_tax=_money(walk.sales_tax) if bought else None,
        listing_cost=_money(walk.listing_cost) if bought else None,
        net_proceeds=_money(net) if bought else None,
        profit=_money(net - walk.cost) if bought else None,
        margin_percent=_optional_money(margin),
        output_slippage_percent=_optional_money(slippage),
        limit_reason=walk.limit_reason,
        flags=tuple(walk.flags),
        missing_data=walk.missing,
        input_volume_m3=volume * walk.units if volume and bought else None,
        materials=walk.materials,
        input_history_average=_optional_money(history.average)
        if history is not None and history.average
        else None,
        input_history_daily_volume=history.volume if history is not None else None,
        input_history_missing_days=history.missing if history is not None else None,
        input_history_newest_date=history.start if history is not None else None,
        input_price_vs_history_percent=_optional_money(walk.history_vs_input),
        worst_material_name=walk.worst_material[0] if walk.worst_material else None,
        worst_material_days_of_volume=_optional_money(walk.worst_material[1])
        if walk.worst_material
        else None,
    )


def _ordered_rows(
    walks: list[_Walk], options: ScrapmetalOptions
) -> tuple[ScrapmetalDealRow, ...]:
    """Group by scenario, ranked rows first, each part by margin descending."""
    rows: list[ScrapmetalDealRow] = []
    for scenario in SCENARIOS:
        scenario_walks = [walk for walk in walks if walk.scenario == scenario]

        def key(walk: _Walk) -> tuple[bool, Decimal, str, int]:
            margin = walk.margin()
            return (
                not _is_ranked(walk, options),
                -margin if margin is not None else Decimal("Infinity"),
                walk.record.name,
                walk.record.type_id,
            )

        rank = 0
        for walk in sorted(scenario_walks, key=key):
            ranked = _is_ranked(walk, options)
            rank += ranked
            rows.append(_deal_row(walk, rank=rank if ranked else None))
    return tuple(rows)


def _listing_prices(summaries: OrderSummaryDataset) -> dict[int, Decimal]:
    """Return the hub 5% sell price per type."""
    return {
        type_id: price
        for type_id, sides in summaries.records.items()
        if (price := sides.sell_5) is not None
    }


def collect_scrapmetal_deals(
    *,
    hub: MarketHub,
    response: MarketOrdersResponse,
    orders: MarketOrdersDataset,
    summaries: OrderSummaryDataset,
    types: TypesDataset,
    type_materials: TypeMaterialsDataset,
    market_groups: MarketGroupsDataset,
    history: HistoryLookup | None,
    options: ScrapmetalOptions,
    generated_at: Instant,
) -> ScrapmetalHubReport:
    """Find items that can be bought in a hub system and reprocessed for a profit.

    Args:
        hub: Hub whose system orders are used to buy items and sell materials.
        response: Regional order snapshot metadata.
        orders: Regional orders for that snapshot.
        summaries: Hub-system order summaries calculated from the same orders.
        types: Static types, including unpublished material types.
        type_materials: Static fixed reprocessing materials.
        market_groups: Static market groups.
        history: Optional regional history lookup for context flags.
        options: Calculation options.
        generated_at: Shared generation time used for staleness.

    Returns:
        All profitable, thin, and incomplete deal rows for the hub.

    Raises:
        ValueError: If the response, orders, and summaries disagree on scope.
    """
    _validate_snapshot(hub=hub, response=response, summaries=summaries, orders=orders)
    sells, buys = _hub_orders(orders, hub.system_id)
    listing_prices = _listing_prices(summaries)
    generated_on = date.fromisoformat(generated_at.format_iso()[:10])
    walks: list[_Walk] = []
    for type_id in eligible_input_ids(
        types=types, type_materials=type_materials, market_groups=market_groups
    ):
        if type_id not in sells:
            continue
        record = types[type_id]
        materials = recovered_materials(
            type_id=type_id,
            types=types,
            type_materials=type_materials,
            yield_percent=options.yield_percent,
        )
        if not materials:
            continue
        unmarketable = {
            m.type_id
            for m in materials
            if (material_type := types.get(m.type_id)) is None
            or material_type.market_group_id not in market_groups
        }
        assert record.market_group_id is not None
        walks += _evaluate_input(
            record=record,
            market_path_names=market_groups[record.market_group_id].str_path,
            materials=materials,
            unmarketable=unmarketable,
            sells=sells[type_id],
            buys=buys,
            listing_prices=listing_prices,
            options=options,
        )
    if history is not None:
        for walk in walks:
            if walk.portions:
                _attach_history(walk, history=history, generated_on=generated_on)
    dated = [walk.history for walk in walks if walk.history is not None]
    return ScrapmetalHubReport(
        schema_version=SCHEMA_VERSION,
        response_metadata_id=response.response_metadata_id,
        received_at=response.received_at,
        expires_at=response.expires_at,
        argus_expires_at=response.argus_expires_at,
        region_id=hub.region_id,
        region_name=hub.region_name,
        system_id=hub.system_id,
        system_name=hub.system_name,
        generated_at=generated_at.format_iso(),
        is_stale=_is_stale(response, generated_at),
        options=options,
        history_oldest_date=min((h.end for h in dated), default=None),
        history_newest_date=max((h.start for h in dated), default=None),
        records=_ordered_rows(walks, options),
    )


def _unit_value(
    materials: tuple[RecoveredMaterial, ...],
    prices: dict[int, Decimal],
    portion_size: int,
) -> Decimal | None:
    """Value one unit from per-portion materials; None if any price is missing."""
    total = Decimal(0)
    for material in materials:
        price = prices.get(material.type_id)
        if price is None:
            return None
        total += price * material.quantity
    return _money(total / portion_size)


def _hub_material_prices(
    inputs: HubPriceInputs, material_ids: set[int]
) -> tuple[dict[str, dict[int, Decimal]], str | None]:
    """Collect buy, sell, and history prices per material at one hub.

    Returns:
        Prices keyed by value kind then material type ID, and the newest history
        date used.
    """
    prices: dict[str, dict[int, Decimal]] = {"buy": {}, "sell": {}, "history": {}}
    newest: str | None = None
    for type_id in sorted(material_ids):
        sides = inputs.summaries.records.get(type_id)
        if sides is not None and sides.buy_5 is not None:
            prices["buy"][type_id] = sides.buy_5
        if sides is not None and sides.sell_5 is not None:
            prices["sell"][type_id] = sides.sell_5
        summary = inputs.history(type_id) if inputs.history is not None else None
        if summary is not None and summary.average:
            prices["history"][type_id] = summary.average
            newest = summary.start if newest is None else max(newest, summary.start)
    return prices, newest


def collect_scrapmetal_price_points(
    *,
    hubs: Sequence[HubPriceInputs],
    types: TypesDataset,
    type_materials: TypeMaterialsDataset,
    market_groups: MarketGroupsDataset,
    yield_percent: Decimal,
    generated_at: Instant,
) -> ScrapmetalPricePointsReport:
    """Value one unit of every eligible item by its recovered materials per hub.

    Values are gross (before fees, hauling, and margin) and empty when any recovered
    material lacks a price; a missing price is never treated as zero.

    Raises:
        ValueError: If a hub's response and summaries disagree on scope.
    """
    ScrapmetalOptions(yield_percent=yield_percent)
    inputs_ids = eligible_input_ids(
        types=types, type_materials=type_materials, market_groups=market_groups
    )
    materials_by_type = {
        type_id: recovered_materials(
            type_id=type_id,
            types=types,
            type_materials=type_materials,
            yield_percent=yield_percent,
        )
        for type_id in inputs_ids
    }
    material_ids = {
        material.type_id
        for materials in materials_by_type.values()
        for material in materials
    }
    sources: list[HubPriceSource] = []
    hub_prices: list[tuple[str, dict[str, dict[int, Decimal]]]] = []
    for inputs in hubs:
        _validate_snapshot(
            hub=inputs.hub, response=inputs.response, summaries=inputs.summaries
        )
        prices, newest = _hub_material_prices(inputs, material_ids)
        hub_prices.append((inputs.hub.system_name, prices))
        sources.append(
            HubPriceSource(
                region_id=inputs.hub.region_id,
                system_id=inputs.hub.system_id,
                system_name=inputs.hub.system_name,
                response_metadata_id=inputs.response.response_metadata_id,
                orders_received_at=inputs.response.received_at,
                is_stale=_is_stale(inputs.response, generated_at),
                history_newest_date=newest,
            )
        )
    rows: list[ScrapmetalPricePointRow] = []
    for type_id, materials in materials_by_type.items():
        record = types[type_id]
        assert record.market_group_id is not None
        values = tuple(
            HubUnitValues(
                system_name=name,
                buy=_unit_value(materials, prices["buy"], record.portion_size),
                sell=_unit_value(materials, prices["sell"], record.portion_size),
                history=_unit_value(materials, prices["history"], record.portion_size),
            )
            for name, prices in hub_prices
        )
        best: tuple[str, Decimal] | None = None
        for value in values:
            if value.buy is not None and (best is None or value.buy > best[1]):
                best = (value.system_name, value.buy)
        rows.append(
            ScrapmetalPricePointRow(
                type_id=type_id,
                type_name=record.name,
                market_group_id=record.market_group_id,
                market_path_names=market_groups[record.market_group_id].str_path,
                portion_size=record.portion_size,
                unit_volume_m3=_unit_volume(record),
                values=values,
                best_buy_hub=best[0] if best is not None else None,
                best_buy_value=best[1] if best is not None else None,
            )
        )
    rows.sort(key=lambda row: (row.market_path_names, row.type_name, row.type_id))
    return ScrapmetalPricePointsReport(
        schema_version=SCHEMA_VERSION,
        generated_at=generated_at.format_iso(),
        yield_percent=yield_percent,
        hubs=tuple(sources),
        records=tuple(rows),
    )
