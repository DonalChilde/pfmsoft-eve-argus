"""Generate the prototype reprocessing value reference report."""

import argparse
import asyncio
import csv
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
DEFAULT_CSV_FILENAME = PROOF_OUTPUT_DIR / "reprocessing_value_report.csv"
DEFAULT_DEALS_REPORT_FILENAME = PROOF_OUTPUT_DIR / "reprocessing_deals_report.md"
DEFAULT_DEALS_CSV_FILENAME = PROOF_OUTPUT_DIR / "reprocessing_deals.csv"
YIELD_PERCENT = 55
CSV_FIELDNAMES = (
    "input_type_id",
    "input_name",
    "market_path",
    "portion_size",
    "yield_percent",
    "hub",
    "input_buy_price",
    "input_sell_price",
    "reprocessed_buy_value",
    "reprocessed_sell_value",
    "missing_data",
    "input_status",
)
DEAL_CSV_FIELDNAMES = (
    "input_type_id",
    "input_name",
    "market_path",
    "portion_size",
    "yield_percent",
    "source_hub",
    "output_hub",
    "deal_scope",
    "deal_direction",
    "input_price",
    "input_price_side",
    "recovered_value",
    "recovered_value_side",
    "cost",
    "revenue",
    "gross_profit",
    "margin_percent",
    "market_status",
    "missing_data",
)


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
    input_rows = sorted(
        (row for row in rows if row["role"] == "Input"),
        key=lambda row: (row["market_path"] or "Unclassified", row["name"]),
    )
    current_market_path: str | None = None
    for input_row in input_rows:
        item_rows = [
            row
            for row in rows
            if row is input_row or row.get("input_type_id") == input_row["type_id"]
        ]
        market_path = input_row["market_path"] or "Unclassified"
        if market_path != current_market_path:
            lines.extend([f"## Market path: {market_path}", ""])
            current_market_path = market_path
        lines.extend([
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


def build_csv_rows(
    rows: list[dict[str, Any]], hub_names: list[str], yield_percent: int = YIELD_PERCENT
) -> list[dict[str, object]]:
    """Build one normalized value row per input item and hub."""
    csv_rows: list[dict[str, object]] = []
    input_rows = [row for row in rows if row["role"] == "Input"]
    for input_row in input_rows:
        item_rows = [
            row
            for row in rows
            if row is input_row or row.get("input_type_id") == input_row["type_id"]
        ]
        material_rows = item_rows[1:]
        for hub_name in hub_names:
            input_prices = input_row["prices"].get(hub_name, {})
            buy_value, buy_missing = calculate_value(material_rows, hub_name, "buy")
            sell_value, sell_missing = calculate_value(material_rows, hub_name, "sell")
            missing = sorted(set(buy_missing + sell_missing))
            csv_rows.append(
                {
                    "input_type_id": input_row["type_id"],
                    "input_name": input_row["name"],
                    "market_path": input_row["market_path"],
                    "portion_size": input_row["quantity"],
                    "yield_percent": yield_percent,
                    "hub": hub_name,
                    "input_buy_price": input_prices.get("buy", ""),
                    "input_sell_price": input_prices.get("sell", ""),
                    "reprocessed_buy_value": buy_value or "",
                    "reprocessed_sell_value": sell_value or "",
                    "missing_data": "; ".join(missing),
                    "input_status": input_row["status"],
                }
            )
    return csv_rows


def write_csv(rows: list[dict[str, object]], output_path: Path) -> None:
    """Write normalized value rows to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def build_deal_rows(
    rows: list[dict[str, Any]],
    hub_names: list[str],
    yield_percent: int = YIELD_PERCENT,
) -> list[dict[str, Any]]:
    """Calculate local and cross-hub deal rows in both directions."""
    deal_rows: list[dict[str, Any]] = []
    input_rows = [row for row in rows if row["role"] == "Input"]
    for input_row in input_rows:
        item_rows = [
            row
            for row in rows
            if row is input_row or row.get("input_type_id") == input_row["type_id"]
        ]
        material_rows = item_rows[1:]
        value_cache = {
            (hub_name, side): calculate_value(material_rows, hub_name, side)
            for hub_name in hub_names
            for side in ("buy", "sell")
        }
        for source_hub in hub_names:
            input_prices = input_row["prices"].get(source_hub, {})
            for output_hub in hub_names:
                for direction in (
                    "buy_input_sell_materials",
                    "sell_input_buy_materials",
                ):
                    if direction == "buy_input_sell_materials":
                        input_price_side = "buy"
                        recovered_value_side = "sell"
                        input_price = input_prices.get("buy")
                        recovered_value, missing = value_cache[(output_hub, "sell")]
                    else:
                        input_price_side = "sell"
                        recovered_value_side = "buy"
                        input_price = input_prices.get("sell")
                        recovered_value, missing = value_cache[(output_hub, "buy")]

                    missing_data = list(missing)
                    if input_price is None:
                        missing_data.insert(0, f"input {input_price_side} price")
                    cost = input_price if direction == "buy_input_sell_materials" else recovered_value
                    revenue = recovered_value if direction == "buy_input_sell_materials" else input_price
                    gross_profit = (
                        revenue - cost
                        if cost is not None and revenue is not None
                        else None
                    )
                    margin_percent = (
                        gross_profit / cost * Decimal(100)
                        if gross_profit is not None and cost
                        else None
                    )
                    deal_rows.append(
                        {
                            "input_type_id": input_row["type_id"],
                            "input_name": input_row["name"],
                            "market_path": input_row["market_path"],
                            "portion_size": input_row["quantity"],
                            "yield_percent": yield_percent,
                            "source_hub": source_hub,
                            "output_hub": output_hub,
                            "deal_scope": "local"
                            if source_hub == output_hub
                            else "cross_hub",
                            "deal_direction": direction,
                            "input_price": input_price,
                            "input_price_side": input_price_side,
                            "recovered_value": recovered_value,
                            "recovered_value_side": recovered_value_side,
                            "cost": cost,
                            "revenue": revenue,
                            "gross_profit": gross_profit,
                            "margin_percent": margin_percent,
                            "market_status": "complete" if not missing_data else "incomplete",
                            "missing_data": sorted(set(missing_data)),
                        }
                    )
    return deal_rows


def render_deals_report(
    deal_rows: list[dict[str, Any]],
    minimum_margin: Decimal = Decimal(0),
) -> str:
    """Render positive deals and concise exception notes as Markdown."""
    ranked_rows = [
        row
        for row in deal_rows
        if row["gross_profit"] is not None
        and row["gross_profit"] > 0
        and row["margin_percent"] is not None
        and row["margin_percent"] >= minimum_margin
    ]
    ranked_rows.sort(key=lambda row: row["gross_profit"], reverse=True)
    incomplete_rows = [row for row in deal_rows if row["market_status"] != "complete"]
    lines = [
        "# Reprocessing Deals Report",
        "",
        f"Minimum gross margin: {minimum_margin}%",
        "Status: PROVISIONAL - excludes hauling, taxes, broker fees, and route costs",
        "",
        "## Ranked opportunities",
        "",
        "| Rank | Input item | Source hub | Output hub | Deal direction | Cost | Revenue | Gross profit | Margin | Data quality |",
        "| ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for rank, row in enumerate(ranked_rows, start=1):
        lines.append(
            f"| {rank} | {markdown_cell(row['input_name'])} | {row['source_hub']} | "
            f"{row['output_hub']} | {row['deal_direction']} | "
            f"{format_decimal(row['cost'])} | {format_decimal(row['revenue'])} | "
            f"{format_decimal(row['gross_profit'])} | "
            f"{format_decimal(row['margin_percent'])}% | {row['market_status']} |"
        )
    lines.extend(
        [
            "",
            f"Ranked opportunities: {len(ranked_rows)} of {len(deal_rows)} deal rows.",
            "",
            "## Exception notes",
            "",
            "Routine opportunities do not receive duplicate detail sections.",
            "The following sample shows incomplete rows that require explanation.",
            "",
            "| Input item | Source hub | Output hub | Deal direction | Missing data | Impact |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in incomplete_rows[:25]:
        lines.append(
            f"| {markdown_cell(row['input_name'])} | {row['source_hub']} | "
            f"{row['output_hub']} | {row['deal_direction']} | "
            f"{markdown_cell('; '.join(row['missing_data']))} | "
            "Excluded from ranked opportunities |"
        )
    if len(incomplete_rows) > 25:
        lines.append(f"| ... | ... | ... | ... | {len(incomplete_rows) - 25} more rows | ... |")
    lines.append("")
    return "\n".join(lines)


def build_deals_csv_rows(deal_rows: list[dict[str, Any]]) -> list[dict[str, object]]:
    """Convert deal rows to spreadsheet-safe values."""
    return [
        {
            **row,
            "missing_data": "; ".join(row["missing_data"]),
        }
        for row in deal_rows
    ]


def write_deals_csv(rows: list[dict[str, object]], output_path: Path) -> None:
    """Write all deal comparison rows to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=DEAL_CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


async def generate_value_report(
    limit: int | None,
    output_path: Path,
    csv_output_path: Path,
    deals_output_path: Path,
    deals_csv_output_path: Path,
    minimum_margin: Decimal,
) -> None:
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
    csv_rows = build_csv_rows(
        rows=rows,
        hub_names=[hub.system_name for hub in MARKET_HUBS],
    )
    write_csv(csv_rows, csv_output_path)
    deal_rows = build_deal_rows(
        rows=rows,
        hub_names=[hub.system_name for hub in MARKET_HUBS],
    )
    deals_report = render_deals_report(
        deal_rows=deal_rows,
        minimum_margin=minimum_margin,
    )
    deals_output_path.parent.mkdir(parents=True, exist_ok=True)
    deals_output_path.write_text(deals_report, encoding="utf-8")
    deals_csv_rows = build_deals_csv_rows(deal_rows)
    write_deals_csv(deals_csv_rows, deals_csv_output_path)
    print(
        f"Wrote {len([row for row in rows if row['role'] == 'Input'])} inputs to "
        f"{output_path}, {len(csv_rows)} value rows to {csv_output_path}, "
        f"and {len(deal_rows)} deal rows to {deals_output_path} and "
        f"{deals_csv_output_path}"
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
    parser.add_argument(
        "--csv-output",
        type=Path,
        default=DEFAULT_CSV_FILENAME,
        help="CSV output path.",
    )
    parser.add_argument(
        "--deals-output",
        type=Path,
        default=DEFAULT_DEALS_REPORT_FILENAME,
        help="Deals Markdown output path.",
    )
    parser.add_argument(
        "--deals-csv-output",
        type=Path,
        default=DEFAULT_DEALS_CSV_FILENAME,
        help="Deals CSV output path.",
    )
    parser.add_argument(
        "--minimum-margin",
        type=Decimal,
        default=Decimal(0),
        help="Minimum gross margin percentage for ranked opportunities.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    asyncio.run(
        generate_value_report(
            arguments.limit,
            arguments.output,
            arguments.csv_output,
            arguments.deals_output,
            arguments.deals_csv_output,
            arguments.minimum_margin,
        )
    )
