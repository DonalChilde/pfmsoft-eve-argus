"""Generate read-only station-trades proof reports from stored EVE data.

The prototype uses a provisional four-significant-figure tick pending in-game
verification.
"""

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter
from contextlib import ExitStack, closing
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any

from whenever import Instant

from pfmsoft.eve_argus.dynamic import models as dynamic_models
from pfmsoft.eve_argus.dynamic import order_summary
from pfmsoft.eve_argus.dynamic import read as dynamic_read
from pfmsoft.eve_argus.helpers.currency import as_currency
from pfmsoft.eve_argus.helpers.file_safe_string import file_safe_string
from pfmsoft.eve_argus.helpers.markdown import format_markdown, markdown_cell
from pfmsoft.eve_argus.market_history import history_summary
from pfmsoft.eve_argus.market_history import models as history_models
from pfmsoft.eve_argus.market_history import read as history_read
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS, MarketHub
from pfmsoft.eve_argus.static import models as static_models
from pfmsoft.eve_argus.static import read as static_read

ROOT = Path(__file__).resolve().parents[3]
ORDER_DATABASE = ROOT / "dev/app-dir/argus-dynamic-db.sqlite"
HISTORY_DATABASE = ROOT / "dev/app-dir/market-history-db.sqlite"
STATIC_DATABASE = (
    ROOT / "dev/app-dir/static-db-store/build_3607705_2026-10-12T11_08_38Z_sqlite"
)
HISTORY_DAYS = 10
HISTORY_STALE_DAYS = 7
MARKDOWN_ROW_LIMIT = 100
PARTICIPATION_PERCENT = Decimal("1")
ACQUISITION_BROKER_FEE_PERCENT = Decimal("0")
SALE_BROKER_FEE_PERCENT = Decimal("0")
SALES_TAX_PERCENT = Decimal("0")
MINIMUM_MARKET_TICK = Decimal("0.01")
PRICE_POLICY = (
    "four significant figures, minimum 0.01 ISK tick; provisional pending "
    "in-game verification"
)
COMPETITION_SCOPE = "station_anchored_only"

STATION_CSV_FIELDS = (
    "generated_at",
    "order_response_metadata_id",
    "orders_received_at",
    "orders_expires_at",
    "orders_argus_expires_at",
    "orders_expiry_used",
    "orders_freshness",
    "region_id",
    "region_name",
    "system_id",
    "system_name",
    "station_id",
    "station_name",
    "type_id",
    "type_name",
    "market_group_id",
    "market_path",
    "status",
    "rank",
    "flags",
    "missing_data",
    "competition_scope",
    "participation_percent",
    "history_window_days",
    "acquisition_broker_fee_percent",
    "sale_broker_fee_percent",
    "sales_tax_percent",
    "summary_filter_factor",
    "price_policy",
    "best_station_buy_price",
    "best_station_sell_price",
    "proposed_buy_price",
    "proposed_sell_price",
    "five_percent_buy_price",
    "five_percent_sell_price",
    "station_buy_remaining_quantity",
    "station_sell_remaining_quantity",
    "station_buy_order_count",
    "station_sell_order_count",
    "station_buy_order_context",
    "station_sell_order_context",
    "five_percent_buy_depth_order_count",
    "five_percent_buy_depth_quantity",
    "five_percent_sell_depth_order_count",
    "five_percent_sell_depth_quantity",
    "history_received_at",
    "history_expires_at",
    "history_argus_expires_at",
    "history_freshness",
    "history_window_start_date",
    "history_window_end_date",
    "history_oldest_date_used",
    "history_newest_date_used",
    "history_missing_days",
    "regional_history_average_price",
    "regional_average_daily_volume",
    "regional_average_daily_order_count",
    "proposed_buy_deviation_percent",
    "proposed_sell_deviation_percent",
    "gross_spread_per_unit",
    "acquisition_broker_fee_per_unit",
    "sale_broker_fee_per_unit",
    "sales_tax_per_unit",
    "acquisition_cost_per_unit",
    "net_sale_proceeds_per_unit",
    "net_profit_per_unit",
    "net_margin_percent",
    "estimated_daily_units",
    "estimated_daily_net_profit",
    "daily_acquisition_broker_fee",
    "daily_sale_broker_fee",
    "daily_sales_tax",
    "modeled_acquisition_capital",
    "modeled_sale_listing_cost",
    "one_day_order_units",
    "one_day_order_acquisition_capital",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class HistoryWindow:
    """One common consecutive calendar window for a region."""

    newest_date: str
    oldest_date: str
    dates: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ProofTypeRecord:
    """Minimum static type fields needed by this standalone proof."""

    type_id: int
    market_group_id: int | None
    name: str
    published: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class UnitEconomics:
    """Unrounded one-unit and optional daily-scenario economics."""

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


@dataclass(frozen=True, slots=True, kw_only=True)
class SideSummary:
    """Station-scoped 5% depth and summary metrics for one side of the book."""

    five_price: Decimal
    five_orders: int
    five_items: int
    total_items: int
    total_orders: int
    filtered_items: int
    filtered_orders: int


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderContext:
    """Raw station order details retained for later competition review."""

    order_id: int
    price: Decimal
    volume_remain: int
    range: str
    min_volume: int


@dataclass(frozen=True, slots=True, kw_only=True)
class HistoryMetrics:
    """Regional history coverage and volume summary for one candidate type."""

    received_at: str | None
    expires_at: str | None
    argus_expires_at: str | None
    freshness: str
    oldest_date_used: str | None
    newest_date_used: str | None
    missing_days: int | None
    average_price: Decimal | None
    average_daily_volume: Decimal | None
    average_daily_order_count: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class StationCandidate:
    """One eligible (station, type) opportunity candidate."""

    type_id: int
    type_name: str
    market_group_id: int
    market_path: str
    status: str
    rank: int | None
    flags: tuple[str, ...]
    missing_data: tuple[str, ...]
    best_station_buy_price: Decimal | None
    best_station_sell_price: Decimal | None
    proposed_buy_price: Decimal | None
    proposed_sell_price: Decimal | None
    five_percent_buy: SideSummary | None
    five_percent_sell: SideSummary | None
    station_buy_remaining_quantity: int
    station_sell_remaining_quantity: int
    station_buy_order_count: int
    station_sell_order_count: int
    station_buy_order_context: tuple[OrderContext, ...]
    station_sell_order_context: tuple[OrderContext, ...]
    history: HistoryMetrics
    economics: UnitEconomics | None


@dataclass(frozen=True, slots=True, kw_only=True)
class StationTradeReport:
    """One primary-station report with its source provenance and candidates."""

    hub: MarketHub
    generated_at: str
    order_response_metadata_id: int
    orders_received_at: str
    orders_expires_at: str | None
    orders_argus_expires_at: str | None
    orders_expiry_used: str | None
    orders_freshness: str
    history_window: HistoryWindow | None
    warnings: tuple[str, ...]
    records: tuple[StationCandidate, ...]


def open_database(path: Path) -> sqlite3.Connection:
    """Open an existing SQLite database in read-only URI mode."""
    if not path.is_file():
        raise FileNotFoundError(f"Database does not exist: {path}")
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def select_history_window(
    *, newest_stored_date: str, generation_date: date
) -> HistoryWindow:
    """Create the configured window, ending strictly before generation day."""
    newest = date.fromisoformat(newest_stored_date)
    if newest >= generation_date:
        raise ValueError("History end date must be strictly before generation date.")
    dates = tuple(
        (newest - timedelta(days=offset)).isoformat() for offset in range(HISTORY_DAYS)
    )
    return HistoryWindow(
        newest_date=dates[0],
        oldest_date=dates[-1],
        dates=dates,
    )


def calculate_unit_economics(
    *,
    buy_price: Decimal,
    sell_price: Decimal,
    acquisition_broker_fee_percent: Decimal,
    sale_broker_fee_percent: Decimal,
    sales_tax_percent: Decimal,
    regional_daily_volume: Decimal | None,
    participation_percent: Decimal,
) -> UnitEconomics:
    """Calculate proportional fees and throughput without assigning tick prices."""
    rates = (
        acquisition_broker_fee_percent,
        sale_broker_fee_percent,
        sales_tax_percent,
    )
    if any(not rate.is_finite() or rate < 0 or rate > 100 for rate in rates):
        raise ValueError("Fee percentages must be finite values from 0 through 100.")
    if (
        not participation_percent.is_finite()
        or participation_percent <= 0
        or participation_percent > 100
    ):
        raise ValueError("Participation must be finite and greater than 0 through 100.")
    if not buy_price.is_finite() or buy_price <= 0:
        raise ValueError("Buy price must be finite and positive.")
    if not sell_price.is_finite() or sell_price <= 0:
        raise ValueError("Sell price must be finite and positive.")
    if regional_daily_volume is not None and (
        not regional_daily_volume.is_finite() or regional_daily_volume < 0
    ):
        raise ValueError("Regional daily volume must be finite and non-negative.")

    acquisition_fee = buy_price * acquisition_broker_fee_percent / 100
    sale_fee = sell_price * sale_broker_fee_percent / 100
    sales_tax = sell_price * sales_tax_percent / 100
    acquisition_cost = buy_price + acquisition_fee
    net_sale_proceeds = sell_price - sale_fee - sales_tax
    net_profit = net_sale_proceeds - acquisition_cost
    margin = net_profit / acquisition_cost * 100
    daily_units = (
        regional_daily_volume * participation_percent / 100
        if regional_daily_volume is not None
        else None
    )
    one_day_units = int(daily_units) if daily_units is not None else None
    return UnitEconomics(
        acquisition_broker_fee_per_unit=acquisition_fee,
        sale_broker_fee_per_unit=sale_fee,
        sales_tax_per_unit=sales_tax,
        acquisition_cost_per_unit=acquisition_cost,
        net_sale_proceeds_per_unit=net_sale_proceeds,
        net_profit_per_unit=net_profit,
        net_margin_percent=margin,
        estimated_daily_units=daily_units,
        estimated_daily_net_profit=(
            daily_units * net_profit if daily_units is not None else None
        ),
        daily_acquisition_broker_fee=(
            daily_units * acquisition_fee if daily_units is not None else None
        ),
        daily_sale_broker_fee=daily_units * sale_fee
        if daily_units is not None
        else None,
        daily_sales_tax=daily_units * sales_tax if daily_units is not None else None,
        modeled_acquisition_capital=(
            daily_units * acquisition_cost if daily_units is not None else None
        ),
        modeled_sale_listing_cost=(
            daily_units * sale_fee if daily_units is not None else None
        ),
        one_day_order_units=one_day_units,
        one_day_order_acquisition_capital=(
            Decimal(one_day_units) * acquisition_cost
            if one_day_units is not None
            else None
        ),
    )


def market_tick(price: Decimal) -> Decimal:
    """Return a four-significant-figure tick, with a 0.01 ISK minimum."""
    if not price.is_finite() or price <= 0:
        raise ValueError("Market tick price must be finite and positive.")
    return max(
        MINIMUM_MARKET_TICK,
        Decimal(1).scaleb(price.adjusted() - 3),
    )


def _next_higher_price(price: Decimal) -> Decimal:
    """Return the next price grid point strictly above the reference."""
    tick = market_tick(price)
    ticks = (price / tick).to_integral_value(rounding=ROUND_FLOOR) + 1
    return ticks * tick


def _next_lower_price(price: Decimal) -> Decimal | None:
    """Return the closest positive grid point strictly below the reference."""
    exponent = price.adjusted()
    is_power_of_ten = price == Decimal(1).scaleb(exponent)
    tick = market_tick(price)
    if is_power_of_ten:
        tick = max(MINIMUM_MARKET_TICK, Decimal(1).scaleb(exponent - 4))
    ticks = (price / tick).to_integral_value(rounding=ROUND_CEILING) - 1
    result = ticks * tick
    return result if result > 0 else None


def proposed_price_targets(
    *, best_buy: Decimal | None, best_sell: Decimal | None
) -> tuple[Decimal | None, Decimal | None, bool]:
    """Apply provisional significant-figure ticks to both best-price sides."""
    proposed_buy = _next_higher_price(best_buy) if best_buy is not None else None
    proposed_sell = _next_lower_price(best_sell) if best_sell is not None else None
    invalid_target = (best_sell is not None and proposed_sell is None) or (
        proposed_buy is not None
        and proposed_sell is not None
        and proposed_buy >= proposed_sell
    )
    return proposed_buy, proposed_sell, invalid_target


def evaluate_opportunity(
    *,
    best_buy: Decimal | None,
    best_sell: Decimal | None,
    regional_daily_volume: Decimal | None,
) -> tuple[str, Decimal | None, Decimal | None, UnitEconomics | None]:
    """Set status and economics using explicit missing-data precedence."""
    proposed_buy, proposed_sell, invalid_target = proposed_price_targets(
        best_buy=best_buy,
        best_sell=best_sell,
    )
    if best_buy is None:
        return "missing_buy", proposed_buy, proposed_sell, None
    if best_sell is None:
        return "missing_sell", proposed_buy, proposed_sell, None

    economics: UnitEconomics | None = None
    if proposed_buy is not None and proposed_sell is not None:
        economics = calculate_unit_economics(
            buy_price=proposed_buy,
            sell_price=proposed_sell,
            acquisition_broker_fee_percent=ACQUISITION_BROKER_FEE_PERCENT,
            sale_broker_fee_percent=SALE_BROKER_FEE_PERCENT,
            sales_tax_percent=SALES_TAX_PERCENT,
            regional_daily_volume=regional_daily_volume,
            participation_percent=PARTICIPATION_PERCENT,
        )
    if invalid_target:
        return "invalid_price_target", proposed_buy, proposed_sell, economics
    if regional_daily_volume is None:
        return "missing_history", proposed_buy, proposed_sell, economics
    if regional_daily_volume == 0:
        return "zero_history_volume", proposed_buy, proposed_sell, economics
    if economics is None:
        raise ValueError("Valid two-sided books must have calculable price targets.")
    if economics.net_profit_per_unit <= 0:
        return "unprofitable", proposed_buy, proposed_sell, economics
    return "ranked", proposed_buy, proposed_sell, economics


def _rank_key(
    record: StationCandidate,
) -> tuple[Decimal, Decimal, str, int]:
    """Sort ranked rows by exact daily profit, then margin/name/ID."""
    economics = record.economics
    if (
        record.status != "ranked"
        or economics is None
        or economics.estimated_daily_net_profit is None
    ):
        raise ValueError(f"Candidate {record.type_id} is missing ranking metrics.")
    return (
        -economics.estimated_daily_net_profit,
        -economics.net_margin_percent,
        record.type_name.casefold(),
        record.type_id,
    )


def _expiry_state(expiry: str | None, *, generated_at: str) -> str:
    """Return a freshness label without treating unknown expiry as fresh."""
    if expiry is None:
        return "unknown"
    return (
        "expired"
        if Instant.parse_iso(expiry) <= Instant.parse_iso(generated_at)
        else "fresh"
    )


def _side_summary(
    summary: dynamic_models.OrderSummaryRecord | None,
) -> SideSummary | None:
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


def station_active_orders(
    orders: tuple[dynamic_models.MarketOrderRecord, ...],
    *,
    response_metadata_id: int,
    region_id: int,
    type_id: int,
    station_id: int,
) -> tuple[dynamic_models.MarketOrderRecord, ...]:
    """Select valid, remaining orders anchored at exactly one station."""
    station_orders = tuple(order for order in orders if order.location_id == station_id)
    for order in station_orders:
        if (
            order.response_metadata_id != response_metadata_id
            or order.region_id != region_id
            or order.type_id != type_id
        ):
            raise ValueError(
                f"Order {order.order_id} has inconsistent provenance or scope."
            )
        if order.volume_remain < 0:
            raise ValueError(f"Order {order.order_id} has negative remaining volume.")
        if order.volume_remain > 0 and order.price <= 0:
            raise ValueError(
                f"Active station order {order.order_id} has nonpositive price."
            )
    return tuple(order for order in station_orders if order.volume_remain > 0)


def _validate_static_path(
    *,
    type_id: int,
    type_record: ProofTypeRecord,
    market_groups: static_models.MarketGroupsDataset,
) -> tuple[int, str] | None:
    """Validate static identity and return a required market-group path."""
    if type_record.type_id != type_id:
        raise ValueError(f"Static type key does not match type ID {type_id}.")
    if not type_record.published or type_record.market_group_id is None:
        return None
    group = market_groups.get(type_record.market_group_id)
    if group is None or group.market_group_id != type_record.market_group_id:
        raise ValueError(
            f"Missing or inconsistent market group {type_record.market_group_id} "
            f"for type {type_id}."
        )
    if (
        not group.int_path
        or len(group.int_path) != len(group.str_path)
        or group.int_path[-1] != group.market_group_id
        or group.str_path[-1] != group.name
    ):
        raise ValueError(
            f"Invalid static market path for group {group.market_group_id}."
        )
    return group.market_group_id, group.str_path_str()


def _read_proof_types(connection: sqlite3.Connection) -> dict[int, ProofTypeRecord]:
    """Read only the stable static type columns needed by this proof."""
    return {
        row[0]: ProofTypeRecord(
            type_id=row[0],
            market_group_id=row[1],
            name=row[2],
            published=bool(row[3]),
        )
        for row in connection.execute(
            """
            SELECT type_id, market_group_id, name, published
            FROM types
            ORDER BY type_id
            """
        )
    }


def _history_metrics(
    *,
    connection: sqlite3.Connection | None,
    hub: MarketHub,
    type_id: int,
    window: HistoryWindow | None,
    generation_date: date,
) -> HistoryMetrics:
    if connection is None or window is None:
        return HistoryMetrics(
            received_at=None,
            expires_at=None,
            argus_expires_at=None,
            freshness="missing",
            oldest_date_used=None,
            newest_date_used=None,
            missing_days=None,
            average_price=None,
            average_daily_volume=None,
            average_daily_order_count=None,
        )
    records = history_read.market_history_date_range(
        connection,
        region_id=hub.region_id,
        type_id=type_id,
        start=window.newest_date,
        end=window.oldest_date,
    )
    if not records:
        return HistoryMetrics(
            received_at=None,
            expires_at=None,
            argus_expires_at=None,
            freshness="missing",
            oldest_date_used=None,
            newest_date_used=None,
            missing_days=HISTORY_DAYS,
            average_price=None,
            average_daily_volume=None,
            average_daily_order_count=None,
        )
    return calculate_history_metrics(
        records=records,
        hub=hub,
        type_id=type_id,
        window=window,
        generation_date=generation_date,
    )


def calculate_history_metrics(
    *,
    records: tuple[history_models.MarketHistoryRecord, ...],
    hub: MarketHub,
    type_id: int,
    window: HistoryWindow,
    generation_date: date,
) -> HistoryMetrics:
    """Summarize observed regional records over the common calendar window."""
    if any(
        record.region_id != hub.region_id or record.type_id != type_id
        for record in records
    ):
        raise ValueError(
            f"History scope is inconsistent for region/type {hub.region_id}/{type_id}."
        )
    if any(record.date not in window.dates for record in records):
        raise ValueError(
            f"History date is outside the selected window for type {type_id}."
        )

    summary = history_summary.calculate_history_summary(
        records=records,
        dates=window.dates,
    )
    newest_used = max(record.date for record in records)
    oldest_used = min(record.date for record in records)
    age_days = (generation_date - date.fromisoformat(newest_used)).days
    freshness = "stale" if age_days > HISTORY_STALE_DAYS else "current"
    metadata = max(records, key=lambda record: record.received_at)
    return HistoryMetrics(
        received_at=metadata.received_at,
        expires_at=metadata.expires_at,
        argus_expires_at=metadata.argus_expires_at,
        freshness=freshness,
        oldest_date_used=oldest_used,
        newest_date_used=newest_used,
        missing_days=summary.missing,
        average_price=summary.average if summary.volume > 0 else None,
        average_daily_volume=summary.volume,
        average_daily_order_count=summary.order_count,
    )


def _collect_report(
    *,
    hub: MarketHub,
    response: dynamic_models.MarketOrdersResponse,
    order_dataset: dynamic_models.MarketOrdersDataset,
    types: dict[int, ProofTypeRecord],
    market_groups: static_models.MarketGroupsDataset,
    history_connection: sqlite3.Connection | None,
    generated_at: str,
    generation_date: date,
    history_window: HistoryWindow | None,
) -> StationTradeReport:
    """Collect and validate one hub's station candidates from explicit sources."""
    if (
        response.region_id != hub.region_id
        or order_dataset.region_id != hub.region_id
        or order_dataset.response_metadata_id != response.response_metadata_id
        or order_dataset.received_at != response.received_at
        or order_dataset.expires_at != response.expires_at
        or order_dataset.argus_expires_at != response.argus_expires_at
    ):
        raise ValueError(f"Order response provenance does not match {hub.system_name}.")

    station_orders: dict[int, list[dynamic_models.MarketOrderRecord]] = {}
    summary_records: dict[int, dynamic_models.BuySellOrders] = {}
    for type_id, book in order_dataset.records.items():
        all_orders = (*book.buy_orders, *book.sell_orders)
        active_buys = tuple(
            order for order in book.buy_orders if order.volume_remain > 0
        )
        active_sells = tuple(
            order for order in book.sell_orders if order.volume_remain > 0
        )
        for order in all_orders:
            if order.response_metadata_id != response.response_metadata_id:
                raise ValueError(f"Order {order.order_id} has inconsistent provenance.")
            if order.region_id != hub.region_id or order.type_id != type_id:
                raise ValueError(f"Order {order.order_id} has inconsistent scope.")
        active = station_active_orders(
            all_orders,
            response_metadata_id=response.response_metadata_id,
            region_id=hub.region_id,
            type_id=type_id,
            station_id=hub.station_id,
        )
        if active:
            station_orders[type_id] = list(active)
        summary_records[type_id] = dynamic_models.BuySellOrders(
            buy_orders=active_buys,
            sell_orders=active_sells,
        )

    active_dataset = dynamic_models.MarketOrdersDataset(
        response_metadata_id=order_dataset.response_metadata_id,
        received_at=order_dataset.received_at,
        expires_at=order_dataset.expires_at,
        argus_expires_at=order_dataset.argus_expires_at,
        region_id=order_dataset.region_id,
        records=summary_records,
    )
    summaries = order_summary.calculate_dataset_summaries(
        active_dataset,
        location_id=hub.station_id,
        filter_factor=order_summary.FILTER_FACTOR_DEFAULT,
    )
    if (
        summaries.response_metadata_id != response.response_metadata_id
        or summaries.received_at != response.received_at
        or summaries.expires_at != response.expires_at
        or summaries.argus_expires_at != response.argus_expires_at
        or summaries.region_id != hub.region_id
        or summaries.location_id != hub.station_id
        or summaries.system_id is not None
    ):
        raise ValueError(
            f"Station summary provenance is inconsistent for {hub.system_name}."
        )

    expiry = response.argus_expires_at or response.expires_at
    order_freshness = _expiry_state(expiry, generated_at=generated_at)
    warnings: list[str] = [
        "Proposed prices use a provisional four-significant-figure tick with a "
        "0.01 ISK minimum; verify this rule in game.",
        "Buy-order competition is station-anchored only; wider-range competition is incomplete.",
        "All fee rates are 0%; estimates must not be interpreted as net of real fees.",
    ]
    if order_freshness == "expired":
        warnings.append(
            "The selected order snapshot is expired; it is rendered without refresh."
        )
    elif order_freshness == "unknown":
        warnings.append("The selected order snapshot has unknown expiry.")
    if history_connection is None:
        warnings.append("History database is unavailable; history metrics are unknown.")
    elif history_window is None:
        warnings.append(
            "No eligible regional history date was stored before generation."
        )

    rows: list[StationCandidate] = []
    excluded_without_group = 0
    for type_id, orders in sorted(station_orders.items()):
        type_record = types.get(type_id)
        if type_record is None:
            raise ValueError(
                f"Missing static type {type_id} for {hub.station_name} orders; "
                "verify the static build selected by --static-database."
            )
        path = _validate_static_path(
            type_id=type_id,
            type_record=type_record,
            market_groups=market_groups,
        )
        if path is None:
            excluded_without_group += 1
            continue
        group_id, market_path = path
        station_buys = [
            order
            for order in orders
            if order.is_buy_order and order.location_id == hub.station_id
        ]
        station_sells = [
            order
            for order in orders
            if not order.is_buy_order and order.location_id == hub.station_id
        ]
        side_summaries = summaries.records.get(type_id)
        buy_summary = (
            _side_summary(side_summaries.buy_summary) if side_summaries else None
        )
        sell_summary = (
            _side_summary(side_summaries.sell_summary) if side_summaries else None
        )
        history = _history_metrics(
            connection=history_connection,
            hub=hub,
            type_id=type_id,
            window=history_window,
            generation_date=generation_date,
        )
        best_buy = max((order.price for order in station_buys), default=None)
        best_sell = min((order.price for order in station_sells), default=None)
        status, proposed_buy, proposed_sell, economics = evaluate_opportunity(
            best_buy=best_buy,
            best_sell=best_sell,
            regional_daily_volume=history.average_daily_volume,
        )
        flags = ["incomplete_competition_coverage", "zero_fee_assumptions"]
        flags.append("provisional_four_sig_tick_min_0.01")
        missing_data: list[str] = []
        if not station_buys:
            flags.append("missing_buy")
            missing_data.append("station_buy_book")
        if not station_sells:
            flags.append("missing_sell")
            missing_data.append("station_sell_book")
        if history.freshness == "missing":
            flags.append("missing_history")
            missing_data.append("regional_history")
        elif history.freshness == "stale":
            flags.append("stale_history")
        if history.average_daily_volume == 0:
            flags.append("zero_history_volume")
        if status == "invalid_price_target":
            flags.append("invalid_price_target")
        if order_freshness == "expired":
            flags.append("expired_orders")
        elif order_freshness == "unknown":
            flags.append("unknown_order_expiry")
        rows.append(
            StationCandidate(
                type_id=type_id,
                type_name=type_record.name,
                market_group_id=group_id,
                market_path=market_path,
                status=status,
                rank=None,
                flags=tuple(flags),
                missing_data=tuple(dict.fromkeys(missing_data)),
                best_station_buy_price=best_buy,
                best_station_sell_price=best_sell,
                proposed_buy_price=proposed_buy,
                proposed_sell_price=proposed_sell,
                five_percent_buy=buy_summary,
                five_percent_sell=sell_summary,
                station_buy_remaining_quantity=sum(
                    order.volume_remain for order in station_buys
                ),
                station_sell_remaining_quantity=sum(
                    order.volume_remain for order in station_sells
                ),
                station_buy_order_count=len(station_buys),
                station_sell_order_count=len(station_sells),
                station_buy_order_context=tuple(
                    OrderContext(
                        order_id=order.order_id,
                        price=order.price,
                        volume_remain=order.volume_remain,
                        range=order.range,
                        min_volume=order.min_volume,
                    )
                    for order in station_buys
                ),
                station_sell_order_context=tuple(
                    OrderContext(
                        order_id=order.order_id,
                        price=order.price,
                        volume_remain=order.volume_remain,
                        range=order.range,
                        min_volume=order.min_volume,
                    )
                    for order in station_sells
                ),
                history=history,
                economics=economics,
            )
        )
    if excluded_without_group:
        warnings.append(
            f"Excluded {excluded_without_group} published station type(s) without "
            "a market group."
        )
    if history_window is not None and any(
        row.history.freshness == "stale" for row in rows
    ):
        warnings.append("One or more regional history windows are stale.")
    if any(row.history.freshness == "missing" for row in rows):
        warnings.append(
            "Regional history is missing for one or more candidate types; "
            "daily estimates remain unknown."
        )
    ranked = sorted(
        (row for row in rows if row.status == "ranked"),
        key=_rank_key,
    )
    ranked_records = tuple(
        replace(row, rank=rank) for rank, row in enumerate(ranked, start=1)
    )
    remaining = sorted(
        (row for row in rows if row.status != "ranked"),
        key=lambda row: (row.status, row.type_name.casefold(), row.type_id),
    )
    return StationTradeReport(
        hub=hub,
        generated_at=generated_at,
        order_response_metadata_id=response.response_metadata_id,
        orders_received_at=response.received_at,
        orders_expires_at=response.expires_at,
        orders_argus_expires_at=response.argus_expires_at,
        orders_expiry_used=expiry,
        orders_freshness=order_freshness,
        history_window=history_window,
        warnings=tuple(dict.fromkeys(warnings)),
        records=ranked_records + tuple(remaining),
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if hasattr(value, "__dataclass_fields__"):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _record_csv(record: StationCandidate) -> dict[str, str | int | None]:
    history = record.history
    values: dict[str, str | int | None] = {
        "type_id": record.type_id,
        "type_name": record.type_name,
        "market_group_id": record.market_group_id,
        "market_path": record.market_path,
        "status": record.status,
        "rank": record.rank,
        "flags": ";".join(record.flags),
        "missing_data": ";".join(record.missing_data),
        "competition_scope": COMPETITION_SCOPE,
        "participation_percent": str(PARTICIPATION_PERCENT),
        "history_window_days": HISTORY_DAYS,
        "acquisition_broker_fee_percent": str(ACQUISITION_BROKER_FEE_PERCENT),
        "sale_broker_fee_percent": str(SALE_BROKER_FEE_PERCENT),
        "sales_tax_percent": str(SALES_TAX_PERCENT),
        "summary_filter_factor": str(order_summary.FILTER_FACTOR_DEFAULT),
        "price_policy": PRICE_POLICY,
        "best_station_buy_price": _decimal_or_none(record.best_station_buy_price),
        "best_station_sell_price": _decimal_or_none(record.best_station_sell_price),
        "proposed_buy_price": _decimal_or_none(record.proposed_buy_price),
        "proposed_sell_price": _decimal_or_none(record.proposed_sell_price),
        "five_percent_buy_price": _decimal_or_none(
            record.five_percent_buy.five_price if record.five_percent_buy else None
        ),
        "five_percent_sell_price": _decimal_or_none(
            record.five_percent_sell.five_price if record.five_percent_sell else None
        ),
        "station_buy_remaining_quantity": record.station_buy_remaining_quantity,
        "station_sell_remaining_quantity": record.station_sell_remaining_quantity,
        "station_buy_order_count": record.station_buy_order_count,
        "station_sell_order_count": record.station_sell_order_count,
        "station_buy_order_context": json.dumps(
            _jsonable(record.station_buy_order_context),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "station_sell_order_context": json.dumps(
            _jsonable(record.station_sell_order_context),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "five_percent_buy_depth_order_count": (
            record.five_percent_buy.five_orders if record.five_percent_buy else None
        ),
        "five_percent_buy_depth_quantity": (
            record.five_percent_buy.five_items if record.five_percent_buy else None
        ),
        "five_percent_sell_depth_order_count": (
            record.five_percent_sell.five_orders if record.five_percent_sell else None
        ),
        "five_percent_sell_depth_quantity": (
            record.five_percent_sell.five_items if record.five_percent_sell else None
        ),
        "history_received_at": history.received_at,
        "history_expires_at": history.expires_at,
        "history_argus_expires_at": history.argus_expires_at,
        "history_freshness": history.freshness,
        "history_oldest_date_used": history.oldest_date_used,
        "history_newest_date_used": history.newest_date_used,
        "history_missing_days": history.missing_days,
        "regional_history_average_price": _decimal_or_none(history.average_price),
        "regional_average_daily_volume": _decimal_or_none(history.average_daily_volume),
        "regional_average_daily_order_count": history.average_daily_order_count,
    }
    economics = record.economics
    if economics is not None:
        average = history.average_price
        values.update(
            {
                "proposed_buy_deviation_percent": _decimal_or_none(
                    (record.proposed_buy_price / average - 1) * 100
                    if record.proposed_buy_price is not None
                    and average is not None
                    and average != 0
                    else None
                ),
                "proposed_sell_deviation_percent": _decimal_or_none(
                    (record.proposed_sell_price / average - 1) * 100
                    if record.proposed_sell_price is not None
                    and average is not None
                    and average != 0
                    else None
                ),
                "gross_spread_per_unit": _decimal_or_none(
                    record.proposed_sell_price - record.proposed_buy_price
                    if record.proposed_sell_price is not None
                    and record.proposed_buy_price is not None
                    else None
                ),
                "acquisition_broker_fee_per_unit": _decimal_or_none(
                    economics.acquisition_broker_fee_per_unit
                ),
                "sale_broker_fee_per_unit": _decimal_or_none(
                    economics.sale_broker_fee_per_unit
                ),
                "sales_tax_per_unit": _decimal_or_none(economics.sales_tax_per_unit),
                "acquisition_cost_per_unit": _decimal_or_none(
                    economics.acquisition_cost_per_unit
                ),
                "net_sale_proceeds_per_unit": _decimal_or_none(
                    economics.net_sale_proceeds_per_unit
                ),
                "net_profit_per_unit": _decimal_or_none(economics.net_profit_per_unit),
                "net_margin_percent": _decimal_or_none(economics.net_margin_percent),
                "estimated_daily_units": _decimal_or_none(
                    economics.estimated_daily_units
                ),
                "estimated_daily_net_profit": _decimal_or_none(
                    economics.estimated_daily_net_profit
                ),
                "daily_acquisition_broker_fee": _decimal_or_none(
                    economics.daily_acquisition_broker_fee
                ),
                "daily_sale_broker_fee": _decimal_or_none(
                    economics.daily_sale_broker_fee
                ),
                "daily_sales_tax": _decimal_or_none(economics.daily_sales_tax),
                "modeled_acquisition_capital": _decimal_or_none(
                    economics.modeled_acquisition_capital
                ),
                "modeled_sale_listing_cost": _decimal_or_none(
                    economics.modeled_sale_listing_cost
                ),
                "one_day_order_units": economics.one_day_order_units,
                "one_day_order_acquisition_capital": _decimal_or_none(
                    economics.one_day_order_acquisition_capital
                ),
            }
        )
    return values


def _decimal_or_none(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def _display_money(value: Decimal | None) -> str:
    return format(as_currency(value), "f") if value is not None else ""


def _display_decimal(value: Decimal | None) -> str:
    return format(value, "f") if value is not None else ""


def _display_percent(value: Decimal | None) -> str:
    return f"{value.quantize(Decimal('0.01'))}%" if value is not None else ""


def _price_deviation_percent(
    price: Decimal | None, average_price: Decimal | None
) -> Decimal | None:
    if price is None or average_price is None or average_price == 0:
        return None
    return (price / average_price - 1) * 100


def report_payload(report: StationTradeReport) -> dict[str, Any]:
    """Build the JSON document and preserve exact Decimal strings."""
    generated = report.generated_at
    generation_date = datetime.fromisoformat(generated.replace("Z", "+00:00")).date()
    warning_list = list(report.warnings)
    statuses = Counter(record.status for record in report.records)
    return {
        "schema_version": 1,
        "report": "station-trades",
        "scope": _jsonable(report.hub),
        "generated_at": generated,
        "orders": {
            "response_metadata_id": report.order_response_metadata_id,
            "received_at": report.orders_received_at,
            "expires_at": report.orders_expires_at,
            "argus_expires_at": report.orders_argus_expires_at,
            "expiry_used": report.orders_expiry_used,
            "freshness": report.orders_freshness,
        },
        "history": {
            "window_days": HISTORY_DAYS,
            "window_start_date": (
                report.history_window.oldest_date if report.history_window else None
            ),
            "window_end_date": (
                report.history_window.newest_date if report.history_window else None
            ),
            "stale_after_days": HISTORY_STALE_DAYS,
            "generation_date_utc": generation_date.isoformat(),
        },
        "assumptions": {
            "price_policy": PRICE_POLICY,
            "minimum_market_tick_isk": str(MINIMUM_MARKET_TICK),
            "market_tick_significant_figures": 4,
            "market_tick_verification": "provisional; user will verify in game",
            "competition_scope": COMPETITION_SCOPE,
            "participation_percent": str(PARTICIPATION_PERCENT),
            "acquisition_broker_fee_percent": str(ACQUISITION_BROKER_FEE_PERCENT),
            "sale_broker_fee_percent": str(SALE_BROKER_FEE_PERCENT),
            "sales_tax_percent": str(SALES_TAX_PERCENT),
            "summary_filter_factor": str(order_summary.FILTER_FACTOR_DEFAULT),
            "ranked_row_limit_markdown": MARKDOWN_ROW_LIMIT,
            "capital_constraints_modeled": False,
            "repricing_costs_modeled": False,
            "history_is_regional_not_station_specific": True,
        },
        "warnings": warning_list,
        "summary": {
            "candidate_count": len(report.records),
            "ranked_count": sum(record.status == "ranked" for record in report.records),
            "unranked_count": sum(
                record.status != "ranked" for record in report.records
            ),
            "status_counts": dict(sorted(statuses.items())),
        },
        "records": [_jsonable(record) for record in report.records],
    }


def render_station_json(report: StationTradeReport) -> str:
    """Render the station report as indented JSON with exact decimal strings."""
    return json.dumps(report_payload(report), ensure_ascii=False, indent=2) + "\n"


def render_station_csv(report: StationTradeReport) -> str:
    """Render all candidates in the stable proof CSV schema."""
    from io import StringIO

    output = StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=STATION_CSV_FIELDS,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for record in report.records:
        row: dict[str, str | int | None] = {
            "generated_at": report.generated_at,
            "order_response_metadata_id": report.order_response_metadata_id,
            "orders_received_at": report.orders_received_at,
            "orders_expires_at": report.orders_expires_at,
            "orders_argus_expires_at": report.orders_argus_expires_at,
            "orders_expiry_used": report.orders_expiry_used,
            "orders_freshness": report.orders_freshness,
            "region_id": report.hub.region_id,
            "region_name": report.hub.region_name,
            "system_id": report.hub.system_id,
            "system_name": report.hub.system_name,
            "station_id": report.hub.station_id,
            "station_name": report.hub.station_name,
            **_record_csv(record),
        }
        if report.history_window is not None:
            row["history_window_start_date"] = report.history_window.oldest_date
            row["history_window_end_date"] = report.history_window.newest_date
        writer.writerow(row)
    return output.getvalue()


def render_station_markdown(report: StationTradeReport) -> str:
    """Render a concise review view and format it with the shared Markdown helper."""
    hub = report.hub
    ranked = [record for record in report.records if record.status == "ranked"]
    status_counts = Counter(
        record.status for record in report.records if record.status != "ranked"
    )
    lines = [
        f"# Station trades: {markdown_cell(hub.system_name)}",
        "",
        f"- **Station:** {markdown_cell(hub.station_name)} (`{hub.station_id}`)",
        f"- **System:** {markdown_cell(hub.system_name)} (`{hub.system_id}`)",
        f"- **Region:** {markdown_cell(hub.region_name)} (`{hub.region_id}`)",
        f"- **Generated:** {report.generated_at}",
        f"- **Orders:** response `{report.order_response_metadata_id}`, "
        f"received `{report.orders_received_at}`, expiry "
        f"`{report.orders_expiry_used or 'unknown'}` "
        f"({report.orders_freshness})",
    ]
    if report.history_window is None:
        lines.append("- **History window:** unavailable")
    else:
        lines.append(
            f"- **History window:** {report.history_window.oldest_date} through "
            f"{report.history_window.newest_date} ({HISTORY_DAYS} calendar days)"
        )
    lines.extend(
        [
            "",
            f"> **Provisional price assumption:** order prices use four significant "
            f"figures, with a minimum tick of {MINIMUM_MARKET_TICK} ISK. Verify "
            "this rule in game.",
            "",
            "> **Competition limitation:** buy-order competition is station-anchored "
            "only. Wider-range orders may compete but are not modeled.",
            "",
            "> **Fee assumption:** acquisition broker fee, sale broker fee, and sales "
            "tax are all 0%; any real fees are excluded.",
            "",
            f"Assumed regional participation: {PARTICIPATION_PERCENT}%. Regional "
            "history is not station volume or a fill forecast. No capital limits or "
            "repricing costs are modeled.",
            "",
            "## Ranked opportunities",
            "",
            "Price deviations compare each proposed price with the regional history "
            "average; blank values mean the average is unavailable.",
            "",
            "| Rank | Type | Market path | Best buy | Best sell | Proposed buy | Proposed sell | Net profit / unit | Net margin | Regional average | Regional daily volume | Modeled daily units | Estimated daily net profit | Acquisition capital | Station orders / 5% depth | History coverage | Buy deviation | Sell deviation | Flags |",
            "| ---- | ---- | ----------- | -------- | --------- | ------------ | ------------- | ----------------- | ---------- | ---------------- | --------------------- | ------------------ | -------------------------- | ------------------- | ------------------------- | ---------------- | ------------- | -------------- | ----- |",
        ]
    )
    for record in ranked[:MARKDOWN_ROW_LIMIT]:
        economics = record.economics
        if economics is None:
            raise ValueError(f"Ranked candidate {record.type_id} has no economics.")
        lines.append(
            "| "
            + " | ".join(
                (
                    str(record.rank),
                    f"{markdown_cell(record.type_name)} (`{record.type_id}`)",
                    markdown_cell(record.market_path),
                    _display_money(record.best_station_buy_price),
                    _display_money(record.best_station_sell_price),
                    _display_money(record.proposed_buy_price),
                    _display_money(record.proposed_sell_price),
                    _display_money(economics.net_profit_per_unit),
                    _display_percent(economics.net_margin_percent),
                    _display_money(record.history.average_price),
                    _display_decimal(record.history.average_daily_volume),
                    _display_decimal(economics.estimated_daily_units),
                    _display_money(economics.estimated_daily_net_profit),
                    _display_money(economics.modeled_acquisition_capital),
                    (
                        f"{record.station_buy_order_count}/"
                        f"{record.station_buy_remaining_quantity}; "
                        f"{record.station_sell_order_count}/"
                        f"{record.station_sell_remaining_quantity}; "
                        f"5% buy "
                        f"{record.five_percent_buy.five_orders}/"
                        f"{record.five_percent_buy.five_items}, sell "
                        f"{record.five_percent_sell.five_orders}/"
                        f"{record.five_percent_sell.five_items}"
                        if record.five_percent_buy and record.five_percent_sell
                        else "depth unavailable"
                    ),
                    (
                        f"{record.history.oldest_date_used or ''} to "
                        f"{record.history.newest_date_used or ''}; "
                        f"{record.history.missing_days} missing"
                        if record.history.missing_days is not None
                        else "missing"
                    ),
                    _display_percent(
                        _price_deviation_percent(
                            record.proposed_buy_price, record.history.average_price
                        )
                    ),
                    _display_percent(
                        _price_deviation_percent(
                            record.proposed_sell_price, record.history.average_price
                        )
                    ),
                    markdown_cell("; ".join(record.flags)),
                )
            )
            + " |"
        )
    if not ranked:
        lines.append(
            "| "
            + " | ".join(["No opportunities meet the ranking criteria"] + [""] * 18)
            + " |"
        )
    lines.extend(
        [
            "",
            "## Fee details",
            "",
            "| Rank | Type | Acquisition broker fee / unit | Sale broker fee / unit | Sales tax / unit | Daily acquisition broker fee | Daily sale broker fee | Daily sales tax |",
            "| ---- | ---- | ----------------------------- | ---------------------- | ---------------- | ---------------------------- | ---------------------- | --------------- |",
        ]
    )
    for record in ranked[:MARKDOWN_ROW_LIMIT]:
        economics = record.economics
        if economics is None:
            raise ValueError(f"Ranked candidate {record.type_id} has no economics.")
        lines.append(
            f"| {record.rank} | {markdown_cell(record.type_name)} (`{record.type_id}`) "
            f"| {_display_money(economics.acquisition_broker_fee_per_unit)} "
            f"| {_display_money(economics.sale_broker_fee_per_unit)} "
            f"| {_display_money(economics.sales_tax_per_unit)} "
            f"| {_display_money(economics.daily_acquisition_broker_fee)} "
            f"| {_display_money(economics.daily_sale_broker_fee)} "
            f"| {_display_money(economics.daily_sales_tax)} |"
        )
    lines.extend(["", "## Unranked candidates", ""])
    if status_counts:
        lines.extend(
            f"- **{markdown_cell(status)}:** {count}"
            for status, count in sorted(status_counts.items())
        )
    else:
        lines.append("None.")
    lines.extend(
        [
            "",
            f"CSV and JSON retain all {len(report.records)} candidates.",
            "",
            "## Warnings",
            "",
        ]
    )
    lines.extend(f"- {markdown_cell(warning)}" for warning in report.warnings)
    lines.extend(
        [
            "",
            "## Definitions and limitations",
            "",
            "- **Best buy/sell:** highest remaining station-anchored buy and lowest "
            "remaining station sell prices, respectively.",
            f"- **Proposed prices:** the next legal tick above the best station buy "
            "and below the best station sell, using four significant figures and "
            f"a {MINIMUM_MARKET_TICK} ISK minimum tick.",
            "- **5% price:** a summary depth threshold, not a +/-5% price band or "
            f"execution-price promise. Outlier filtering uses factor "
            f"{order_summary.FILTER_FACTOR_DEFAULT}.",
            "- **Regional volume:** average traded volume per calendar day across "
            "the common history window; it does not identify station share.",
            "- **Participation:** a scenario assumption applied once to completed "
            "buy-then-sell cycles, not a fill probability.",
            "- **Margin:** net profit per unit divided by acquisition cost per unit.",
            "- **Capital:** modeled daily units times acquisition cost per unit; "
            "portfolio constraints are not modeled.",
            "- **Daily profit:** a regional-volume participation scenario, not a "
            "fill forecast or guaranteed profit.",
            "",
        ]
    )
    return format_markdown("\n".join(lines))


def _latest_order_responses(
    connection: sqlite3.Connection,
) -> dict[int, dynamic_models.MarketOrdersResponse]:
    """Select the newest response in each required region, including empty ones."""
    by_region = {
        region_id: dynamic_read.market_orders_responses(connection, region_id=region_id)
        for region_id in dict.fromkeys(hub.region_id for hub in MARKET_HUBS)
    }
    missing = [hub.system_name for hub in MARKET_HUBS if not by_region[hub.region_id]]
    if missing:
        raise ValueError(
            f"No stored regional market orders for: {', '.join(missing)}. "
            "Run 'uv run eve-argus fetch market-orders --hubs' to fetch source orders."
        )
    return {region: responses[0] for region, responses in by_region.items()}


def _history_window_for_region(
    connection: sqlite3.Connection | None,
    *,
    region_id: int,
    generation_date: date,
) -> HistoryWindow | None:
    if connection is None:
        return None
    row = connection.execute(
        "SELECT MAX(date_) FROM market_history WHERE region_id = ? AND date_ < ?",
        (region_id, generation_date.isoformat()),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return select_history_window(
        newest_stored_date=row[0],
        generation_date=generation_date,
    )


def _rendered_files(report: StationTradeReport) -> dict[str, str]:
    """Render every format before any report file is created."""
    component = file_safe_string(report.hub.system_name)
    received = file_safe_string(report.orders_received_at)
    if not component or not received:
        raise ValueError(
            f"Empty sanitized filename component for {report.hub.system_name}."
        )
    stem = f"station-trades-{component}-{report.hub.station_id}-{received}"
    return {
        f"{stem}.md": render_station_markdown(report),
        f"{stem}.csv": render_station_csv(report),
        f"{stem}.json": render_station_json(report),
    }


def write_reports(
    reports: tuple[StationTradeReport, ...],
    *,
    destination: Path,
    overwrite: bool,
) -> tuple[Path, ...]:
    """Preflight all paths, then write rendered files with exclusive creation."""
    rendered = {
        path: content
        for report in reports
        for path, content in _rendered_files(report).items()
    }
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"Report destination is not a directory: {destination}")
    output_paths = tuple(destination / filename for filename in rendered)
    collisions = [path for path in output_paths if path.exists()]
    if collisions and not overwrite:
        raise FileExistsError(
            "Report files already exist; pass --overwrite to replace them: "
            + ", ".join(str(path) for path in collisions)
        )
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for path, content in zip(output_paths, rendered.values(), strict=True):
        if overwrite:
            path.write_text(content, encoding="utf-8", newline="\n")
        else:
            with path.open("x", encoding="utf-8", newline="\n") as output:
                output.write(content)
        written.append(path)
    return tuple(written)


def generate_reports(
    *,
    orders_database: Path,
    history_database: Path,
    static_database: Path,
    generated_at: datetime | None = None,
) -> tuple[StationTradeReport, ...]:
    """Read the selected local snapshots and collect reports without source writes."""
    generation = generated_at or datetime.now(UTC)
    if generation.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware.")
    generation = generation.astimezone(UTC)
    generated_iso = generation.isoformat().replace("+00:00", "Z")
    generation_date = generation.date()

    with ExitStack() as stack:
        dynamic = stack.enter_context(closing(open_database(orders_database)))
        static = stack.enter_context(closing(open_database(static_database)))
        history = (
            stack.enter_context(closing(open_database(history_database)))
            if history_database.is_file()
            else None
        )
        responses = _latest_order_responses(dynamic)
        types = _read_proof_types(static)
        market_groups = static_read.market_groups(static)
        reports: list[StationTradeReport] = []
        windows: dict[int, HistoryWindow | None] = {}
        datasets: dict[int, dynamic_models.MarketOrdersDataset] = {}
        for region_id, response in responses.items():
            datasets[region_id] = dynamic_read.market_orders(
                dynamic, response.response_metadata_id
            )
            windows[region_id] = _history_window_for_region(
                history,
                region_id=region_id,
                generation_date=generation_date,
            )
        for hub in MARKET_HUBS:
            response = responses[hub.region_id]
            reports.append(
                _collect_report(
                    hub=hub,
                    response=response,
                    order_dataset=datasets[hub.region_id],
                    types=types,
                    market_groups=market_groups,
                    history_connection=history,
                    generated_at=generated_iso,
                    generation_date=generation_date,
                    history_window=windows[hub.region_id],
                )
            )
        return tuple(reports)


def main(argv: list[str] | None = None) -> int:
    """Run the proof CLI with explicit local databases and output destination."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--to", type=Path, required=True, help="Report output directory."
    )
    parser.add_argument(
        "--orders-database",
        type=Path,
        default=ORDER_DATABASE,
        help=f"Read-only dynamic database (default: {ORDER_DATABASE}).",
    )
    parser.add_argument(
        "--history-database",
        type=Path,
        default=HISTORY_DATABASE,
        help=f"Read-only market-history database (default: {HISTORY_DATABASE}).",
    )
    parser.add_argument(
        "--static-database",
        type=Path,
        default=STATIC_DATABASE,
        help=f"Read-only static database (default: {STATIC_DATABASE}).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace report files that already exist.",
    )
    args = parser.parse_args(argv)
    try:
        reports = generate_reports(
            orders_database=args.orders_database,
            history_database=args.history_database,
            static_database=args.static_database,
        )
        for report in reports:
            for warning in report.warnings:
                print(f"Warning [{report.hub.system_name}]: {warning}", file=sys.stderr)
        paths = write_reports(
            reports,
            destination=args.to,
            overwrite=args.overwrite,
        )
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
