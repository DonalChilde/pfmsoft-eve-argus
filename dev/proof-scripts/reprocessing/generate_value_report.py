"""Generate the prototype reprocessing value reference report."""

import argparse
import asyncio
import sqlite3
from collections.abc import Iterable
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any

from pfmsoft.eve_argus.data_loaders.esd_datasets import EsdDatasetsLoader
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.market.orders.db import query_helpers as market_queries
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS, MarketHub
from pfmsoft.eve_argus.settings import get_settings
from pfmsoft.eve_argus.static.db import query_helpers as static_queries

PROOF_OUTPUT_DIR = Path(__file__).parent.parent / "proof-output" / "reprocessing"
DEFAULT_REPORT_FILENAME = PROOF_OUTPUT_DIR / "reprocessing_value_report.md"
YIELD_PERCENT = 55


def format_decimal(value: Decimal | None) -> str:
    """Format an ISK value, preserving an empty value for missing prices."""
    if value is None:
        return ""
    return f"{value:,.2f}"


def format_quantity(value: int | None) -> str:
    """Format a material quantity, preserving an empty value when unavailable."""
    if value is None:
        return ""
    return f"{value:,}"


def markdown_cell(value: object) -> str:
    """Render a value safely inside a Markdown table cell."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def recovered_quantity(quantity: int, yield_percent: int = YIELD_PERCENT) -> int:
    """Calculate the integer quantity recovered from one fixed component."""
    return int(
        (Decimal(quantity) * Decimal(yield_percent) / Decimal(100)).quantize(
            Decimal("1"), rounding=ROUND_DOWN
        )
    )


def load_market_groups(database_path: Path) -> dict[int, Any]:
    """Load market groups from the Argus static database."""
    with sqlite3.connect(database_path) as connection:
        return static_queries.get_market_groups(connection)


def load_hub_prices(
    connection: sqlite3.Connection, hub: MarketHub
) -> dict[int, dict[str, Decimal]]:
    """Load persisted 5% prices for one configured hub system."""
    prices: dict[int, dict[str, Decimal]] = {}
    summaries = market_queries.get_order_summaries(
        connection,
        region_id=hub.region_id,
        system_id=hub.system_id,
    )
    for summary in summaries:
        side = "buy" if summary.is_buy_summary else "sell"
        prices.setdefault(summary.type_id, {})[side] = summary.five_price
    return prices


def build_reference_rows(
    *,
    types: dict[int, Any],
    type_materials: dict[int, Any],
    market_groups: dict[int, Any],
    hub_prices: dict[str, dict[int, dict[str, Decimal]]],
    limit: int | None,
) -> list[dict[str, Any]]:
    """Build input and material rows for the reference tables."""
    eligible_types = {
        type_id: record
        for type_id, record in types.items()
        if record.marketGroupID is not None
    }
    rows: list[dict[str, Any]] = []
    input_count = 0

    for input_type_id, input_record in sorted(
        eligible_types.items(), key=lambda item: item[1].name_localized()
    ):
        material_record = type_materials.get(input_type_id)
        materials = material_record.materials if material_record else None
        if not materials:
            continue
        if limit is not None and input_count >= limit:
            break

        input_market_group = market_groups.get(input_record.marketGroupID)
        market_path = (
            " > ".join(input_market_group.str_path) if input_market_group else ""
        )
        input_prices = {
            hub_name: prices.get(input_type_id, {})
            for hub_name, prices in hub_prices.items()
        }
        rows.append({
            "role": "Input",
            "type_id": input_type_id,
            "name": input_record.name_localized(),
            "market_path": market_path,
            "quantity": input_record.portionSize,
            "prices": input_prices,
            "status": "complete",
        })

        input_status = "complete"
        for material in materials:
            material_record_type = eligible_types.get(material.materialTypeID)
            material_name = (
                material_record_type.name_localized()
                if material_record_type
                else f"Unknown type {material.materialTypeID}"
            )
            material_prices = {
                hub_name: prices.get(material.materialTypeID, {})
                for hub_name, prices in hub_prices.items()
            }
            if material_record_type is None:
                input_status = "incomplete"
            rows.append({
                "role": "material",
                "type_id": material.materialTypeID,
                "name": material_name,
                "market_path": market_path,
                "quantity": recovered_quantity(material.quantity),
                "prices": material_prices,
                "status": "complete" if material_record_type else "unclassified",
                "input_type_id": input_type_id,
            })

        rows[-len(materials) - 1]["status"] = input_status
        input_count += 1
    return rows


def calculate_value(
    material_rows: Iterable[dict[str, Any]],
    hub_name: str,
    side: str,
) -> tuple[Decimal | None, list[str]]:
    """Calculate a hub value, returning missing material names separately."""
    total = Decimal(0)
    missing: list[str] = []
    for row in material_rows:
        price = row["prices"].get(hub_name, {}).get(side)
        if row["status"] != "complete" or price is None:
            missing.append(row["name"])
            continue
        total += price * row["quantity"]
    return (None if missing else total), missing


def render_report(
    *,
    rows: list[dict[str, Any]],
    hub_names: list[str],
    yield_percent: int = YIELD_PERCENT,
) -> str:
    """Render the reference and value tables as Markdown."""
    lines = [
        "# Reprocessing Value Report",
        "",
        f"Assumed yield: {yield_percent}% | Order depth: 5%",
        "Status: PROVISIONAL - portion-size semantics require in-game verification",
        "",
    ]
    input_rows = [row for row in rows if row["role"] == "Input"]
    for input_row in input_rows:
        item_rows = [
            row
            for row in rows
            if row is input_row or row.get("input_type_id") == input_row["type_id"]
        ]
        lines.extend([
            f"## Market path: {input_row['market_path'] or 'Unclassified'}",
            "",
            f"### {input_row['name']}",
            "",
            f"Input type ID: {input_row['type_id']} | Portion size: {input_row['quantity']}",
            "",
            "#### Reference prices by hub",
            "",
            "| Role | Item | Quantity per portion | "
            + " | ".join(f"{hub_name} Buy | {hub_name} Sell" for hub_name in hub_names)
            + " | Market status |",
            "| --- | --- | ---: | "
            + " | ".join("---: | ---:" for _ in hub_names)
            + " | --- |",
        ])
        for row in item_rows:
            prices = []
            for hub_name in hub_names:
                hub_price = row["prices"].get(hub_name, {})
                prices.extend([
                    format_decimal(hub_price.get("buy")),
                    format_decimal(hub_price.get("sell")),
                ])
            lines.append(
                "| "
                + " | ".join([
                    markdown_cell(row["role"]),
                    markdown_cell(row["name"]),
                    format_quantity(row["quantity"]),
                    *prices,
                    markdown_cell(row["status"]),
                ])
                + " |"
            )

        lines.extend([
            "",
            "#### Reprocessed value by hub",
            "",
            "| Hub | Input buy price | Input sell price | Reprocessed buy value | "
            "Reprocessed sell value | Missing data |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ])
        material_rows = item_rows[1:]
        for hub_name in hub_names:
            input_prices = input_row["prices"].get(hub_name, {})
            buy_value, buy_missing = calculate_value(material_rows, hub_name, "buy")
            sell_value, sell_missing = calculate_value(material_rows, hub_name, "sell")
            missing = sorted(set(buy_missing + sell_missing))
            lines.append(
                f"| {hub_name} | {format_decimal(input_prices.get('buy'))} | "
                f"{format_decimal(input_prices.get('sell'))} | "
                f"{format_decimal(buy_value)} | {format_decimal(sell_value)} | "
                f"{markdown_cell(', '.join(missing) if missing else 'none')} |"
            )
        lines.append("")
    return "\n".join(lines)


async def generate_value_report(limit: int | None, output_path: Path) -> None:
    """Load source data and write the prototype value report."""
    settings = get_settings()
    market_groups = load_market_groups(settings.argus_static_database)
    resource_manager = EveArgusResources(settings=settings)

    async with resource_manager as resources:
        esd_loader = EsdDatasetsLoader(resources.sd_query_manager)
        types_dataset = esd_loader.types(published=True)
        type_materials_dataset = esd_loader.type_materials()
        hub_prices = {
            hub.system_name: load_hub_prices(resources.order_db_connection, hub)
            for hub in MARKET_HUBS
        }

    rows = build_reference_rows(
        types=types_dataset.dataset,
        type_materials=type_materials_dataset.dataset,
        market_groups=market_groups,
        hub_prices=hub_prices,
        limit=limit,
    )
    report = render_report(
        rows=rows,
        hub_names=[hub.system_name for hub in MARKET_HUBS],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(
        f"Wrote {len([row for row in rows if row['role'] == 'Input'])} inputs to {output_path}"
    )


def parse_args() -> argparse.Namespace:
    """Parse prototype report options."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of input items for a small inspection report.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REPORT_FILENAME,
        help="Markdown output path.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    asyncio.run(generate_value_report(arguments.limit, arguments.output))
