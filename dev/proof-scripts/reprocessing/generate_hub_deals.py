"""Generate per-hub immediate reprocessing arbitrage reports (Scenario A).

For each market hub, find reprocessable items that can be bought now from sell
orders in the hub system and reprocessed for a profit. Two material-sale
scenarios are ranked separately by margin: selling immediately into hub buy
orders (walking the book), and posting sell orders at the hub 5% sell price.
Input prices always walk the hub sell orders. Reprocessing tax, sales tax, and
listing cost (broker fee) are reported as separate ISK columns. Regional history summaries
are optional context (liquidity and price sanity) and never set a trade price.

Run from this directory or by path:
    uv run python dev/proof-scripts/reprocessing/generate_hub_deals.py
"""

import argparse
import asyncio
import csv
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from generate_value_report import (
    EXCLUDED_MARKET_GROUP_IDS,
    PROOF_OUTPUT_DIR,
    YIELD_PERCENT,
    format_decimal,
    markdown_cell,
    recovered_quantity,
)

from pfmsoft.eve_argus.dynamic import models as dynamic_models
from pfmsoft.eve_argus.dynamic import read as dynamic_read
from pfmsoft.eve_argus.dynamic.order_summary import calculate_dataset_summaries
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.market_history import read as history_read
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS, MarketHub
from pfmsoft.eve_argus.settings import get_settings
from pfmsoft.eve_argus.static import read

MAX_PORTIONS = 50_000
HISTORY_MATERIAL_SHARE = Decimal("0.05")
CSV_FIELDNAMES = (
    "hub",
    "scenario",
    "input_type_id",
    "input_name",
    "market_path",
    "portion_size",
    "yield_percent",
    "status",
    "flags",
    "portions",
    "units_to_buy",
    "best_price",
    "worst_price",
    "avg_price",
    "total_cost",
    "gross_proceeds",
    "reprocessing_tax",
    "sales_tax",
    "listing_cost",
    "net_proceeds",
    "profit",
    "margin_percent",
    "output_slippage_percent",
    "limit_reason",
    "input_volume_m3",
    "materials_per_portion",
    "missing_data",
    "input_history_avg_price",
    "input_price_vs_history_percent",
    "input_history_daily_volume",
    "input_history_missing_days",
    "input_history_end",
    "worst_material",
    "worst_material_days_of_volume",
)


class Book:
    """One side of a hub-system order book, consumed best price first."""

    def __init__(self, orders: list[dynamic_models.MarketOrderRecord]) -> None:
        """Initialize from orders already sorted best price first."""
        self.levels = [[order.price, order.volume_remain] for order in orders]
        self.total = sum(volume for _, volume in self.levels)
        self.index = 0
        self.touched: set[int] = set()

    def quote(self, quantity: int) -> tuple[Decimal, Decimal, Decimal] | None:
        """Price a fill without consuming it.

        Returns:
            Total value, first price, and last price; None if depth is too thin.
        """
        if quantity > self.total:
            return None
        remaining = quantity
        value = Decimal(0)
        first = last = Decimal(0)
        index = self.index
        while remaining > 0:
            price, volume = self.levels[index]
            if volume <= 0:
                index += 1
                continue
            take = min(volume, remaining)
            if first == 0:
                first = price
            last = price
            value += price * take
            remaining -= take
            if take == volume:
                index += 1
        return value, first, last

    def take(self, quantity: int) -> None:
        """Consume a fill that was already checked with quote."""
        remaining = quantity
        while remaining > 0:
            volume = self.levels[self.index][1]
            if volume <= 0:
                self.index += 1
                continue
            take = min(volume, remaining)
            self.levels[self.index][1] -= take
            self.touched.add(self.index)
            remaining -= take
            self.total -= take
            if take == volume:
                self.index += 1


IMMEDIATE = "sell_to_buy_orders"
LISTING = "list_sell_orders"
SCENARIOS = (IMMEDIATE, LISTING)


@dataclass(slots=True, kw_only=True)
class DealRow:
    """One hub-local buy-and-reprocess deal under one material-sale scenario."""

    hub: str
    scenario: str
    type_id: int
    name: str
    market_path: str
    portion_size: int
    status: str = "profitable"
    flags: list[str] = field(default_factory=list)
    portions: int = 0
    units: int = 0
    best_price: Decimal | None = None
    worst_price: Decimal | None = None
    cost: Decimal = Decimal(0)
    net_proceeds: Decimal = Decimal(0)
    gross_proceeds: Decimal = Decimal(0)
    reprocessing_tax: Decimal = Decimal(0)
    sales_tax: Decimal = Decimal(0)
    listing_cost: Decimal = Decimal(0)
    best_gross_proceeds: Decimal = Decimal(0)
    limit_reason: str = ""
    volume_m3: float | None = None
    materials: list[tuple[int, str, int]] = field(default_factory=list)
    material_units: dict[int, int] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    history: dict[str, Any] = field(default_factory=dict)

    @property
    def profit(self) -> Decimal:
        """Net proceeds minus cost."""
        return self.net_proceeds - self.cost

    @property
    def margin(self) -> Decimal | None:
        """Profit as a percentage of cost."""
        return self.profit / self.cost * 100 if self.cost else None

    @property
    def slippage(self) -> Decimal | None:
        """Share of best-price proceeds lost to walking down the buy books."""
        if not self.best_gross_proceeds:
            return None
        return (
            (self.best_gross_proceeds - self.gross_proceeds)
            / self.best_gross_proceeds
            * 100
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class Settings:
    """Calculation and reporting options."""

    yield_percent: int
    sales_tax: Decimal
    broker_fee: Decimal
    reprocessing_tax: Decimal
    min_profit: Decimal
    min_margin: Decimal
    max_slippage: Decimal
    history_stale_days: int
    order_stale_minutes: int
    top: int
    use_history: bool

    def fees(self, scenario: str, gross: Decimal) -> tuple[Decimal, Decimal, Decimal]:
        """Return reprocessing tax, sales tax, and listing cost for gross value.

        Listing cost (broker fee) only applies when materials are posted as sell
        orders.
        """
        listing = self.broker_fee if scenario == LISTING else Decimal(0)
        return (
            gross * self.reprocessing_tax,
            gross * self.sales_tax,
            gross * listing,
        )


class BookPricer:
    """Price materials by selling immediately into hub buy orders."""

    def __init__(self, buys: dict[int, list], material_ids: list[int]) -> None:
        """Create one consumable buy book per material."""
        self.books = {mid: Book(buys[mid]) for mid in material_ids}

    def quote(self, material_id: int, quantity: int) -> tuple[Decimal, Decimal] | None:
        """Return walked value and best-price value, or None if depth runs out."""
        quote = self.books[material_id].quote(quantity)
        return None if quote is None else (quote[0], quote[1] * quantity)

    def take(self, material_id: int, quantity: int) -> None:
        """Consume buy-book depth."""
        self.books[material_id].take(quantity)


class FixedPricer:
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


def eligible_inputs(
    *,
    types: dict[int, Any],
    type_materials: dict[int, Any],
    market_groups: dict[int, Any],
) -> list[int]:
    """Select published, market-grouped types that have fixed materials."""
    eligible = []
    for type_id, record in types.items():
        group = market_groups.get(record.market_group_id)
        material_record = type_materials.get(type_id)
        if (
            record.published
            and group is not None
            and not EXCLUDED_MARKET_GROUP_IDS.intersection(group.int_path)
            and material_record is not None
            and material_record.materials
        ):
            eligible.append(type_id)
    return eligible


def hub_books(
    dataset: dynamic_models.MarketOrdersDataset, system_id: int
) -> tuple[dict[int, list], dict[int, list]]:
    """Split the regional dataset into per-type sell and buy orders for a system."""
    sells: dict[int, list] = {}
    buys: dict[int, list] = {}
    for type_id, orders in dataset.records.items():
        sell = [o for o in orders.sell_orders if o.system_id == system_id]
        buy = [o for o in orders.buy_orders if o.system_id == system_id]
        if sell:
            sells[type_id] = sell
        if buy:
            buys[type_id] = buy
    return sells, buys


def listing_prices(
    dataset: dynamic_models.MarketOrdersDataset, *, system_id: int
) -> dict[int, Decimal]:
    """Calculate the listing price per type: the hub 5% sell price."""
    summaries = calculate_dataset_summaries(dataset, system_id=system_id)
    return {
        type_id: sides.sell_summary.five_price
        for type_id, sides in summaries.records.items()
        if sides.sell_summary is not None
    }


def evaluate_input(
    *,
    hub: MarketHub,
    type_id: int,
    types: dict[int, Any],
    type_materials: dict[int, Any],
    market_groups: dict[int, Any],
    sells: dict[int, list],
    buys: dict[int, list],
    list_prices: dict[int, Decimal],
    settings: Settings,
) -> list[DealRow]:
    """Size an immediate buy-and-reprocess deal under each material-sale scenario.

    Returns:
        One row per scenario that is incomplete or has a profitable portion; an
        empty list when the input is not listed in the hub system.
    """
    if type_id not in sells:
        return []
    record = types[type_id]
    materials: list[tuple[int, str, int]] = []
    unmarketable: set[int] = set()
    for material in type_materials[type_id].materials:
        material_type = types.get(material.material_type_id)
        name = (
            material_type.name
            if material_type
            else f"Unknown {material.material_type_id}"
        )
        quantity = recovered_quantity(material.quantity, settings.yield_percent)
        if quantity <= 0:
            continue
        materials.append((material.material_type_id, name, quantity))
        if material_type is None or material_type.market_group_id not in market_groups:
            unmarketable.add(material.material_type_id)
    if not materials:
        return []
    rows = []
    for scenario in SCENARIOS:
        available, label = (
            (buys, "buy orders") if scenario == IMMEDIATE else (list_prices, "5% sell")
        )
        row = DealRow(
            hub=hub.system_name,
            scenario=scenario,
            type_id=type_id,
            name=record.name,
            market_path=" > ".join(market_groups[record.market_group_id].str_path),
            portion_size=record.portion_size,
            volume_m3=record.volume,
            materials=list(materials),
            missing=[
                f"{name} {label}"
                for mid, name, _ in materials
                if mid in unmarketable or mid not in available
            ],
        )
        if row.missing:
            row.status = "incomplete"
            row.best_price = sells[type_id][0].price
            rows.append(row)
            continue
        pricer = (
            BookPricer(buys, [mid for mid, _, _ in materials])
            if scenario == IMMEDIATE
            else FixedPricer(list_prices)
        )
        walk_portions(
            row, input_orders=sells[type_id], pricer=pricer, settings=settings
        )
        if row.portions:
            rows.append(row)
    return rows


def walk_portions(
    row: DealRow,
    *,
    input_orders: list,
    pricer: BookPricer | FixedPricer,
    settings: Settings,
) -> None:
    """Buy and reprocess one portion at a time while each portion stays profitable."""
    input_book = Book(input_orders)
    row.limit_reason = "input supply exhausted"
    for _ in range(MAX_PORTIONS):
        input_quote = input_book.quote(row.portion_size)
        if input_quote is None:
            break
        cost, first, last = input_quote
        gross = Decimal(0)
        best_gross = Decimal(0)
        blocked = ""
        for material_id, name, quantity in row.materials:
            quote = pricer.quote(material_id, quantity)
            if quote is None:
                blocked = f"{name} buy depth exhausted"
                break
            gross += quote[0]
            best_gross += quote[1]
        if blocked:
            row.limit_reason = blocked
            break
        reprocessing_tax, sales_tax, listing_cost = settings.fees(row.scenario, gross)
        net = gross - reprocessing_tax - sales_tax - listing_cost
        marginal = net - cost
        if marginal <= 0 or marginal / cost * 100 < settings.min_margin:
            row.limit_reason = "marginal portion not profitable"
            break
        input_book.take(row.portion_size)
        for material_id, _, quantity in row.materials:
            pricer.take(material_id, quantity)
            row.material_units[material_id] = (
                row.material_units.get(material_id, 0) + quantity
            )
        row.portions += 1
        row.units += row.portion_size
        row.cost += cost
        row.gross_proceeds += gross
        row.best_gross_proceeds += best_gross
        row.net_proceeds += net
        row.reprocessing_tax += reprocessing_tax
        row.sales_tax += sales_tax
        row.listing_cost += listing_cost
        row.best_price = first if row.best_price is None else row.best_price
        row.worst_price = last
    else:
        row.limit_reason = f"capped at {MAX_PORTIONS} portions"
    if (
        row.portions
        and row.slippage is not None
        and row.slippage > settings.max_slippage
    ):
        row.status = "thin"
        row.flags.append("high_output_slippage")


def attach_history(
    row: DealRow,
    *,
    connection: sqlite3.Connection,
    region_id: int,
    cache: dict[int, Any],
    settings: Settings,
    today: datetime,
) -> None:
    """Add liquidity and price-sanity context from regional history summaries."""

    def summary(type_id: int) -> Any:
        if type_id not in cache:
            try:
                cache[type_id] = history_read.history_summary(
                    connection, region_id=region_id, type_id=type_id
                )
            except ValueError:
                cache[type_id] = None
        return cache[type_id]

    input_summary = summary(row.type_id)
    if input_summary is None:
        row.flags.append("input_history_missing")
    else:
        row.history["input_avg"] = input_summary.average
        row.history["input_volume"] = input_summary.volume
        row.history["input_missing_days"] = input_summary.missing
        row.history["input_end"] = input_summary.start
        row.history["oldest"] = input_summary.end
        if input_summary.average and row.best_price:
            row.history["input_vs_avg"] = (
                (row.best_price - input_summary.average) / input_summary.average * 100
            )
            if row.history["input_vs_avg"] < -30:
                row.flags.append("input_far_below_history_avg")
        if (today.date() - datetime.fromisoformat(input_summary.start).date()).days > (
            settings.history_stale_days
        ):
            row.flags.append("history_stale")

    worst: tuple[str, Decimal] | None = None
    for material_id, name, _ in row.materials:
        units = row.material_units.get(material_id, 0)
        if units == 0:
            continue
        material_summary = summary(material_id)
        if material_summary is None or not material_summary.volume:
            continue
        days = Decimal(units) / material_summary.volume
        if worst is None or days > worst[1]:
            worst = (name, days)
    if worst is not None:
        row.history["worst_material"] = worst[0]
        row.history["worst_material_days"] = worst[1]
        if worst[1] > 1:
            row.flags.append("exceeds_daily_volume")
            if row.status == "profitable":
                row.status = "thin"


def is_ranked(row: DealRow, settings: Settings) -> bool:
    """Return whether a row belongs in the actionable Markdown table."""
    margin = row.margin
    return (
        row.status == "profitable"
        and row.profit >= settings.min_profit
        and margin is not None
        and margin >= settings.min_margin
    )


def age_text(received_at: str, now: datetime) -> str:
    """Describe how old a snapshot is."""
    age = now - datetime.fromisoformat(received_at)
    hours = age.total_seconds() / 3600
    return f"{hours:.1f} h ago"


SCENARIO_TITLES = {
    IMMEDIATE: "Sell materials to buy orders (immediate)",
    LISTING: "Post material sell orders at 5% sell price (slow)",
}


def rate_text(rate: Decimal) -> str:
    """Format a fractional rate as a plain percentage number."""
    return format((rate * 100).normalize(), "f")


def margin_key(row: DealRow) -> Decimal:
    """Sort key: margin, with missing margins last."""
    return row.margin if row.margin is not None else Decimal("-Infinity")


def render_ranked_table(
    rows: list[DealRow], *, scenario: str, settings: Settings
) -> list[str]:
    """Render one margin-sorted opportunity table for a scenario."""
    scenario_rows = [row for row in rows if row.scenario == scenario]
    ranked = sorted(
        (row for row in scenario_rows if is_ranked(row, settings)),
        key=margin_key,
        reverse=True,
    )
    counts = {
        name: sum(1 for row in scenario_rows if row.status == name)
        for name in ("profitable", "thin", "incomplete")
    }
    fee_text = (
        f"Rates: reprocessing tax {rate_text(settings.reprocessing_tax)}%, sales tax "
        f"{rate_text(settings.sales_tax)}%"
    )
    is_listing = scenario == LISTING
    match scenario:
        case "sell_to_buy_orders":
            basis = (
                f"Materials are sold immediately by walking hub buy orders. {fee_text}."
            )
        case _:
            basis = (
                "Materials are listed at the hub 5% sell price, assumed to fill in "
                f"full. {fee_text}, listing cost (broker fee) "
                f"{rate_text(settings.broker_fee)}%."
            )
    listing_header = " Listing cost |" if is_listing else ""
    listing_rule = " -----------: |" if is_listing else ""
    lines = [
        f"## {SCENARIO_TITLES[scenario]} (by margin)",
        "",
        basis,
        f"Rows: {counts['profitable']} profitable, {counts['thin']} thin "
        f"(CSV only), {counts['incomplete']} incomplete (CSV only)",
        "",
        "| Rank | Item | Market path | Buy units | Price range | Total cost | "
        f"Gross proceeds | Reprocessing tax | Sales tax |{listing_header} "
        "Net proceeds | Profit | Margin | Limited by | Flags |",
        "| ---: | ---- | ----------- | --------: | ----------: | ---------: | "
        f"-------------: | ---------------: | --------: |{listing_rule} "
        "-----------: | -----: | -----: | ---------- | ----- |",
    ]
    for rank, row in enumerate(ranked[: settings.top], start=1):
        price_range = (
            f"{format_decimal(row.best_price)} - {format_decimal(row.worst_price)}"
        )
        lines.append(
            f"| {rank} | {markdown_cell(row.name)} | "
            f"{markdown_cell(row.market_path)} | {row.units:,} | {price_range} | "
            f"{format_decimal(row.cost)} | {format_decimal(row.gross_proceeds)} | "
            f"{format_decimal(row.reprocessing_tax)} | "
            f"{format_decimal(row.sales_tax)} | "
            + (f"{format_decimal(row.listing_cost)} | " if is_listing else "")
            + f"{format_decimal(row.net_proceeds)} | "
            f"{format_decimal(row.profit)} | {row.margin:.1f}% | "
            f"{markdown_cell(row.limit_reason)} | "
            f"{markdown_cell(', '.join(row.flags))} |"
        )
    if not ranked:
        empty_cells = " |" * (13 if is_listing else 12)
        lines.append(f"| | No opportunities meet the thresholds{empty_cells}")
    if len(ranked) > settings.top:
        lines += ["", f"Showing {settings.top} of {len(ranked)} ranked rows."]
    lines.append("")
    return lines


def render_hub_report(
    *,
    hub: MarketHub,
    rows: list[DealRow],
    snapshot: str,
    settings: Settings,
    now: datetime,
) -> str:
    """Render the actionable Markdown report for one hub."""
    history_dates = [
        (row.history["oldest"], row.history["input_end"])
        for row in rows
        if "input_end" in row.history
    ]
    lines = [
        f"# Reprocessing Deals: {hub.system_name}",
        "",
        f"Buy items from sell orders in {hub.system_name}, reprocess, and sell the "
        f"materials in {hub.system_name}. Status: PROVISIONAL.",
        "",
        f"Generated: {now.isoformat(timespec='seconds')}",
        f"Order snapshot: {snapshot} ({age_text(snapshot, now)})",
    ]
    snapshot_age = now - datetime.fromisoformat(snapshot)
    if snapshot_age.total_seconds() > settings.order_stale_minutes * 60:
        lines.append(
            f"**WARNING: order data is older than {settings.order_stale_minutes} "
            "minutes. Refresh orders before acting.**"
        )
    if history_dates:
        oldest = min(item[0] for item in history_dates)
        newest = max(item[1] for item in history_dates)
        lines.append(f"History used: {oldest} to {newest} (context only)")
    elif settings.use_history:
        lines.append("History used: none available")
    lines += [
        f"Assumed yield: {settings.yield_percent}%",
        f"Thresholds: min profit {format_decimal(settings.min_profit)} ISK, "
        f"min margin {settings.min_margin}%, max output slippage "
        f"{settings.max_slippage}%",
        "Input prices walk the hub sell orders. Order min_volume, transport, and "
        "skills are not modeled.",
        "",
    ]
    for scenario in SCENARIOS:
        lines += render_ranked_table(rows, scenario=scenario, settings=settings)
    lines += render_limit_definitions(settings)
    return "\n".join(lines)


def render_limit_definitions(settings: Settings) -> list[str]:
    """Explain the possible `Limited by` values that stop the purchase walk."""
    return [
        "## `Limited by` definitions",
        "",
        "Items are bought one reprocessing portion at a time, cheapest sell order "
        "first. `Limited by` names the condition that stopped the next portion, so "
        "`Buy units` is the largest quantity that remained worthwhile.",
        "",
        "| Value | Meaning | What to do |",
        "| ----- | ------- | ---------- |",
        "| input supply exhausted | Every hub sell order for the item was bought; "
        "fewer than one more portion remains on the market. | The whole listed "
        "supply is profitable. Watch for restocks. |",
        "| marginal portion not profitable | The next portion would cost more than "
        "its materials return after fees, or its margin would fall below the "
        f"minimum margin ({settings.min_margin}%). Usually the next input sell "
        "order is too expensive or, in the immediate table, material buy orders "
        "have been walked down to lower prices. | Stop at `Buy units`; buying more "
        "loses money or falls below the threshold. |",
        "| `<material>` buy depth exhausted | Immediate table only. Selling the next "
        "portion's materials would need more of that material than the hub buy "
        "orders hold. | The market cannot absorb more of this material now. Sell "
        "the rest later or list it instead. |",
        f"| capped at {MAX_PORTIONS} portions | A safety limit on the purchase "
        "walk was reached before any other condition. | Deal size is understated; "
        "check the market directly. |",
        "",
        "The sell-order table prices materials at a fixed 5% sell price with no "
        "depth limit, so it is only stopped by input supply or the input price. "
        "Use the `exceeds_daily_volume` flag to judge whether the listings would "
        "actually sell.",
        "",
    ]


def csv_row(row: DealRow, settings: Settings) -> dict[str, object]:
    """Flatten a deal row for CSV output."""
    avg_price = row.cost / row.units if row.units else None
    history = row.history
    return {
        "hub": row.hub,
        "scenario": row.scenario,
        "input_type_id": row.type_id,
        "input_name": row.name,
        "market_path": row.market_path,
        "portion_size": row.portion_size,
        "yield_percent": settings.yield_percent,
        "status": row.status,
        "flags": ";".join(row.flags),
        "portions": row.portions,
        "units_to_buy": row.units,
        "best_price": row.best_price if row.best_price is not None else "",
        "worst_price": row.worst_price if row.worst_price is not None else "",
        "avg_price": f"{avg_price:.2f}" if avg_price is not None else "",
        "total_cost": f"{row.cost:.2f}" if row.portions else "",
        "gross_proceeds": f"{row.gross_proceeds:.2f}" if row.portions else "",
        "reprocessing_tax": f"{row.reprocessing_tax:.2f}" if row.portions else "",
        "sales_tax": f"{row.sales_tax:.2f}" if row.portions else "",
        "listing_cost": f"{row.listing_cost:.2f}" if row.portions else "",
        "net_proceeds": f"{row.net_proceeds:.2f}" if row.portions else "",
        "profit": f"{row.profit:.2f}" if row.portions else "",
        "margin_percent": f"{row.margin:.2f}" if row.margin is not None else "",
        "output_slippage_percent": (
            f"{row.slippage:.2f}" if row.slippage is not None else ""
        ),
        "limit_reason": row.limit_reason,
        "input_volume_m3": (
            f"{row.volume_m3 * row.units:.2f}" if row.volume_m3 and row.units else ""
        ),
        "materials_per_portion": ";".join(f"{n} x{q}" for _, n, q in row.materials),
        "missing_data": ";".join(row.missing),
        "input_history_avg_price": (
            f"{history['input_avg']:.2f}" if "input_avg" in history else ""
        ),
        "input_price_vs_history_percent": (
            f"{history['input_vs_avg']:.1f}" if "input_vs_avg" in history else ""
        ),
        "input_history_daily_volume": history.get("input_volume", ""),
        "input_history_missing_days": history.get("input_missing_days", ""),
        "input_history_end": history.get("input_end", ""),
        "worst_material": history.get("worst_material", ""),
        "worst_material_days_of_volume": (
            f"{history['worst_material_days']:.2f}"
            if "worst_material_days" in history
            else ""
        ),
    }


def write_hub_csv(rows: list[DealRow], path: Path, settings: Settings) -> None:
    """Write all rows for a hub, grouped by scenario and sorted by margin."""
    ordered = sorted(
        rows, key=lambda row: (SCENARIOS.index(row.scenario), -margin_key(row))
    )
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(csv_row(row, settings) for row in ordered)


def load_hub_dataset(
    connection: sqlite3.Connection, hub: MarketHub
) -> tuple[dynamic_models.MarketOrdersDataset, str]:
    """Load the newest regional order snapshot for a hub."""
    responses = dynamic_read.market_orders_responses(
        connection, region_id=hub.region_id
    )
    if not responses:
        raise ValueError(f"No stored regional market orders for {hub.system_name}.")
    response = responses[0]
    dataset = dynamic_read.market_orders(
        connection, response_metadata_id=response.response_metadata_id
    )
    return dataset, response.received_at


async def generate(
    *, hub_names: list[str], limit: int | None, output_dir: Path, settings: Settings
) -> None:
    """Generate per-hub reports and CSV files."""
    resources_manager = EveArgusResources(settings=get_settings())
    output_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    async with resources_manager as resources:
        static = resources.argus_static_db_connection
        types = read.types(static, only_published=True)
        type_materials = read.type_materials(static)
        market_groups = read.market_groups(static)
        inputs = eligible_inputs(
            types=types, type_materials=type_materials, market_groups=market_groups
        )
        if limit is not None:
            inputs = inputs[:limit]
        for hub in MARKET_HUBS:
            if hub_names and hub.system_name.lower() not in hub_names:
                continue
            dataset, snapshot = load_hub_dataset(
                resources.argus_dynamic_db_connection, hub
            )
            sells, buys = hub_books(dataset, hub.system_id)
            list_prices = listing_prices(
                dataset,
                system_id=hub.system_id,
            )
            rows = [
                row
                for type_id in inputs
                for row in evaluate_input(
                    hub=hub,
                    type_id=type_id,
                    types=types,
                    type_materials=type_materials,
                    market_groups=market_groups,
                    sells=sells,
                    buys=buys,
                    list_prices=list_prices,
                    settings=settings,
                )
            ]
            if settings.use_history:
                cache: dict[int, Any] = {}
                for row in rows:
                    if row.portions:
                        attach_history(
                            row,
                            connection=resources.market_history_db_connection,
                            region_id=hub.region_id,
                            cache=cache,
                            settings=settings,
                            today=now,
                        )
            stem = hub.system_name.lower()
            report = render_hub_report(
                hub=hub, rows=rows, snapshot=snapshot, settings=settings, now=now
            )
            (output_dir / f"deals_{stem}.md").write_text(report, encoding="utf-8")
            write_hub_csv(rows, output_dir / f"deals_{stem}.csv", settings)
            ranked = {
                scenario: sum(
                    1
                    for row in rows
                    if row.scenario == scenario and is_ranked(row, settings)
                )
                for scenario in SCENARIOS
            }
            print(f"{hub.system_name}: {len(rows)} rows, ranked {ranked}")


def percent(value: str) -> Decimal:
    """Parse a percentage argument into a fraction."""
    return Decimal(value) / 100


def parse_args() -> argparse.Namespace:
    """Parse command line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hubs", nargs="*", default=[], help="Hub names; default all.")
    parser.add_argument("--limit", type=int, default=None, help="Limit input items.")
    parser.add_argument("--output-dir", type=Path, default=PROOF_OUTPUT_DIR)
    parser.add_argument("--yield-percent", type=int, default=YIELD_PERCENT)
    parser.add_argument(
        "--sales-tax", type=percent, default=Decimal(0), help="Percent."
    )
    parser.add_argument(
        "--broker-fee",
        type=percent,
        default=Decimal(0),
        help="Listing cost percent; applies to the sell-order table only.",
    )
    parser.add_argument(
        "--reprocessing-tax", type=percent, default=Decimal(0), help="Percent."
    )
    parser.add_argument("--min-profit", type=Decimal, default=Decimal(100_000))
    parser.add_argument(
        "--min-margin", type=Decimal, default=Decimal(5), help="Percent."
    )
    parser.add_argument(
        "--max-slippage", type=Decimal, default=Decimal(10), help="Percent."
    )
    parser.add_argument("--history-stale-days", type=int, default=7)
    parser.add_argument("--order-stale-minutes", type=int, default=60)
    parser.add_argument("--top", type=int, default=100, help="Max Markdown rows.")
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        generate(
            hub_names=[name.lower() for name in args.hubs],
            limit=args.limit,
            output_dir=args.output_dir,
            settings=Settings(
                yield_percent=args.yield_percent,
                sales_tax=args.sales_tax,
                broker_fee=args.broker_fee,
                reprocessing_tax=args.reprocessing_tax,
                min_profit=args.min_profit,
                min_margin=args.min_margin,
                max_slippage=args.max_slippage,
                history_stale_days=args.history_stale_days,
                order_stale_minutes=args.order_stale_minutes,
                top=args.top,
                use_history=not args.no_history,
            ),
        )
    )
