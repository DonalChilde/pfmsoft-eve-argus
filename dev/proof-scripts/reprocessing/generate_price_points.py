"""Generate a per-unit reprocessed value price list for sourcing items (Scenario B).

For every eligible reprocessable item, calculate the gross value of its
reprocessed materials per unit of the item at each hub. Each value is the
break-even price to bid for the item elsewhere, haul it to that hub, and
reprocess it there (before fees, hauling, and margin). Materials are valued
three ways per hub:

- buy: hub-system 5% buy price (sell materials immediately).
- sell: hub-system 5% sell price (list materials).
- hist: regional 10-day volume-weighted average price (context; may lag orders).

A hub value is left empty when any material lacks that price; it is never
treated as zero. Output is one wide CSV row per item.

Run:
    uv run python dev/proof-scripts/reprocessing/generate_price_points.py
"""

import argparse
import asyncio
import csv
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any

from generate_hub_deals import eligible_inputs, load_hub_dataset
from generate_value_report import PROOF_OUTPUT_DIR, YIELD_PERCENT, recovered_quantity

from pfmsoft.eve_argus.dynamic.order_summary import calculate_dataset_summaries
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.market_history import read as history_read
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS, MarketHub
from pfmsoft.eve_argus.settings import get_settings
from pfmsoft.eve_argus.static import read

DEFAULT_OUTPUT = PROOF_OUTPUT_DIR / "price_points.csv"
VALUE_KINDS = ("buy", "sell", "hist")
CENT = Decimal("0.01")


def hub_material_prices(
    *,
    hub: MarketHub,
    dynamic: sqlite3.Connection,
    history: sqlite3.Connection | None,
    material_ids: set[int],
) -> tuple[dict[str, dict[int, Decimal]], str, str | None]:
    """Collect buy, sell, and history prices for every material at one hub.

    Returns:
        Prices keyed by value kind then material type ID, the order snapshot
        time, and the newest history date used (None without history).
    """
    dataset, snapshot = load_hub_dataset(dynamic, hub)
    summaries = calculate_dataset_summaries(dataset, system_id=hub.system_id)
    prices: dict[str, dict[int, Decimal]] = {kind: {} for kind in VALUE_KINDS}
    for type_id in material_ids:
        sides = summaries.records.get(type_id)
        if sides is None:
            continue
        if sides.buy_summary is not None:
            prices["buy"][type_id] = sides.buy_summary.five_price
        if sides.sell_summary is not None:
            prices["sell"][type_id] = sides.sell_summary.five_price
    history_end = None
    if history is not None:
        for type_id in material_ids:
            try:
                summary = history_read.history_summary(
                    history, region_id=hub.region_id, type_id=type_id
                )
            except ValueError:
                summary = None
            if summary is not None and summary.average:
                prices["hist"][type_id] = summary.average
                history_end = max(history_end or summary.start, summary.start)
    return prices, snapshot, history_end


def unit_value(
    materials: list[tuple[int, int]], prices: dict[int, Decimal], portion_size: int
) -> Decimal | None:
    """Value one unit of an item from its per-portion recovered materials.

    Returns:
        The per-unit value, or None when any material lacks a price.
    """
    total = Decimal(0)
    for material_id, quantity in materials:
        price = prices.get(material_id)
        if price is None:
            return None
        total += price * quantity
    return total / portion_size


def recovered_materials(
    type_materials: dict[int, Any], type_id: int, yield_percent: int
) -> list[tuple[int, int]]:
    """Return (material type ID, recovered quantity) for one portion."""
    return [
        (material.material_type_id, quantity)
        for material in type_materials[type_id].materials
        if (quantity := recovered_quantity(material.quantity, yield_percent)) > 0
    ]


def fieldnames(hub_names: list[str]) -> list[str]:
    """Build the wide CSV header."""
    names = ["type_id", "name", "market_path", "portion_size", "volume_m3"]
    for hub_name in hub_names:
        names += [f"{hub_name.lower()}_{kind}" for kind in VALUE_KINDS]
    names += ["best_buy_hub", "best_buy_value"]
    return names


def build_rows(
    *,
    inputs: list[int],
    types: dict[int, Any],
    type_materials: dict[int, Any],
    market_groups: dict[int, Any],
    hub_prices: dict[str, dict[str, dict[int, Decimal]]],
    yield_percent: int,
) -> list[dict[str, object]]:
    """Build one wide row per eligible item, sorted by market path and name."""
    rows = []
    for type_id in inputs:
        record = types[type_id]
        materials = recovered_materials(type_materials, type_id, yield_percent)
        row: dict[str, object] = {
            "type_id": type_id,
            "name": record.name,
            "market_path": " > ".join(market_groups[record.market_group_id].str_path),
            "portion_size": record.portion_size,
            "volume_m3": record.volume if record.volume is not None else "",
        }
        best: tuple[str, Decimal] | None = None
        for hub_name, prices in hub_prices.items():
            for kind in VALUE_KINDS:
                value = unit_value(materials, prices[kind], record.portion_size)
                row[f"{hub_name.lower()}_{kind}"] = (
                    value.quantize(CENT) if value is not None else ""
                )
                if kind == "buy" and value is not None:
                    if best is None or value > best[1]:
                        best = (hub_name, value)
        row["best_buy_hub"] = best[0] if best else ""
        row["best_buy_value"] = best[1].quantize(CENT) if best else ""
        rows.append(row)
    rows.sort(key=lambda row: (row["market_path"], row["name"]))
    return rows


async def generate(*, output: Path, yield_percent: int, use_history: bool) -> None:
    """Load source data and write the price-point CSV."""
    async with EveArgusResources(settings=get_settings()) as resources:
        static = resources.argus_static_db_connection
        types = read.types(static, only_published=True)
        type_materials = read.type_materials(static)
        market_groups = read.market_groups(static)
        inputs = eligible_inputs(
            types=types, type_materials=type_materials, market_groups=market_groups
        )
        material_ids = {
            material_id
            for type_id in inputs
            for material_id, _ in recovered_materials(
                type_materials, type_id, yield_percent
            )
        }
        hub_prices = {}
        for hub in MARKET_HUBS:
            prices, snapshot, history_end = hub_material_prices(
                hub=hub,
                dynamic=resources.argus_dynamic_db_connection,
                history=resources.market_history_db_connection if use_history else None,
                material_ids=material_ids,
            )
            hub_prices[hub.system_name] = prices
            print(
                f"{hub.system_name}: orders {snapshot}, history through "
                f"{history_end or 'n/a'}"
            )
    rows = build_rows(
        inputs=inputs,
        types=types,
        type_materials=type_materials,
        market_groups=market_groups,
        hub_prices=hub_prices,
        yield_percent=yield_percent,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames(list(hub_prices)))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} items for {len(material_ids)} materials to {output}")


def parse_args() -> argparse.Namespace:
    """Parse command line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--yield-percent", type=int, default=YIELD_PERCENT)
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        generate(
            output=args.output,
            yield_percent=args.yield_percent,
            use_history=not args.no_history,
        )
    )
