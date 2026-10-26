"""Pure JSON, CSV, and Jinja Markdown renderers for scrapmetal reports."""

import csv
import json
from dataclasses import asdict, dataclass, fields
from decimal import Decimal
from io import StringIO

from jinja2 import Environment, PackageLoader, StrictUndefined
from whenever import Instant

from pfmsoft.eve_argus.helpers.markdown import format_markdown, markdown_cell
from pfmsoft.eve_argus.reports.scrapmetal import (
    IMMEDIATE,
    LISTING,
    MAX_PORTIONS,
    SCENARIOS,
    Scenario,
    ScrapmetalDealRow,
    ScrapmetalHubReport,
    ScrapmetalPricePointsReport,
)

MARKDOWN_TOP_ROWS = 100
"""Maximum ranked rows per Markdown table; CSV and JSON keep every row."""
SCENARIO_TITLES: dict[Scenario, str] = {
    IMMEDIATE: "Sell materials to buy orders (immediate)",
    LISTING: "Post material sell orders at 5% sell price (slow)",
}
_DEAL_METADATA_COLUMNS = ("system_name", "received_at", "generated_at", "yield_percent")
DEAL_CSV_COLUMNS = (
    *_DEAL_METADATA_COLUMNS,
    *(field.name for field in fields(ScrapmetalDealRow)),
)


def _json_decimal(value: object) -> str:
    """Use plain decimal strings rather than binary floats or exponent notation."""
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(f"Cannot serialize {type(value).__name__} as JSON.")


def _csv_value(value: object) -> object:
    """Render Decimals exactly and leave None as an empty cell."""
    return format(value, "f") if isinstance(value, Decimal) else value


def render_scrapmetal_deals_json(report: ScrapmetalHubReport) -> str:
    """Render one hub report with exact decimal strings and explicit nulls."""
    return (
        json.dumps(asdict(report), default=_json_decimal, ensure_ascii=False, indent=2)
        + "\n"
    )


def render_scrapmetal_deals_csv(report: ScrapmetalHubReport) -> str:
    """Render every deal row as one LF-terminated CSV record."""
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=DEAL_CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    metadata = {
        "system_name": report.system_name,
        "received_at": report.received_at,
        "generated_at": report.generated_at,
        "yield_percent": _csv_value(report.options.yield_percent),
    }
    for row in report.records:
        values = {field.name: getattr(row, field.name) for field in fields(row)}
        values["market_path_names"] = "/".join(row.market_path_names)
        values["flags"] = ";".join(row.flags)
        values["missing_data"] = ";".join(row.missing_data)
        values["materials"] = ";".join(
            f"{material.name} x{material.quantity}" for material in row.materials
        )
        writer.writerow(
            metadata | {name: _csv_value(value) for name, value in values.items()}
        )
    return stream.getvalue()


@dataclass(slots=True, kw_only=True, frozen=True)
class _ScenarioTable:
    """One margin-ranked Markdown table."""

    title: str
    is_listing: bool
    profitable: int
    thin: int
    incomplete: int
    ranked_total: int
    rows: tuple[ScrapmetalDealRow, ...]


def _scenario_table(report: ScrapmetalHubReport, scenario: Scenario) -> _ScenarioTable:
    rows = [row for row in report.records if row.scenario == scenario]
    ranked = [row for row in rows if row.rank is not None]
    return _ScenarioTable(
        title=SCENARIO_TITLES[scenario],
        is_listing=scenario == LISTING,
        profitable=sum(row.status == "profitable" for row in rows),
        thin=sum(row.status == "thin" for row in rows),
        incomplete=sum(row.status == "incomplete" for row in rows),
        ranked_total=len(ranked),
        rows=tuple(ranked[:MARKDOWN_TOP_ROWS]),
    )


def _isk(value: Decimal | None) -> str:
    return "" if value is None else f"{value:,.2f}"


def _number(value: Decimal) -> str:
    """Format an option value without trailing zeros or exponents."""
    return format(value.normalize(), "f") if value else "0"


def _snapshot_age(report: ScrapmetalHubReport) -> str:
    age = Instant.parse_iso(report.generated_at) - Instant.parse_iso(report.received_at)
    return f"{age.total('hours'):.1f} h"


def render_scrapmetal_deals_markdown(report: ScrapmetalHubReport) -> str:
    """Render the two ranked opportunity tables and `Limited by` definitions."""
    environment = Environment(
        loader=PackageLoader("pfmsoft.eve_argus.templates", "scrapmetal"),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    rendered = environment.get_template(
        "report.md.jinja2",
        globals={"cell": markdown_cell, "isk": _isk, "number": _number},
    ).render(
        report=report,
        snapshot_age=_snapshot_age(report),
        tables=[_scenario_table(report, scenario) for scenario in SCENARIOS],
        top_rows=MARKDOWN_TOP_ROWS,
        max_portions=MAX_PORTIONS,
    )
    return format_markdown(rendered)


def render_scrapmetal_price_points_json(report: ScrapmetalPricePointsReport) -> str:
    """Render price points with per-hub sources and nested per-hub values."""
    return (
        json.dumps(asdict(report), default=_json_decimal, ensure_ascii=False, indent=2)
        + "\n"
    )


def price_points_csv_columns(report: ScrapmetalPricePointsReport) -> tuple[str, ...]:
    """Build the wide header: item, per-hub values, best hub, per-hub sources."""
    hubs = [hub.system_name.lower() for hub in report.hubs]
    return (
        "generated_at",
        "yield_percent",
        "type_id",
        "type_name",
        "market_path_names",
        "portion_size",
        "unit_volume_m3",
        *(f"{hub}_{kind}" for hub in hubs for kind in ("buy", "sell", "hist")),
        "best_buy_hub",
        "best_buy_value",
        *(
            f"{hub}_{name}"
            for hub in hubs
            for name in ("orders_received_at", "history_newest_date")
        ),
    )


def render_scrapmetal_price_points_csv(report: ScrapmetalPricePointsReport) -> str:
    """Render one wide LF-terminated CSV record per item."""
    stream = StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=price_points_csv_columns(report), lineterminator="\n"
    )
    writer.writeheader()
    metadata: dict[str, object] = {
        "generated_at": report.generated_at,
        "yield_percent": _csv_value(report.yield_percent),
    }
    for hub in report.hubs:
        prefix = hub.system_name.lower()
        metadata[f"{prefix}_orders_received_at"] = hub.orders_received_at
        metadata[f"{prefix}_history_newest_date"] = hub.history_newest_date
    for row in report.records:
        values: dict[str, object] = {
            "type_id": row.type_id,
            "type_name": row.type_name,
            "market_path_names": "/".join(row.market_path_names),
            "portion_size": row.portion_size,
            "unit_volume_m3": row.unit_volume_m3,
            "best_buy_hub": row.best_buy_hub,
            "best_buy_value": _csv_value(row.best_buy_value),
        }
        for hub_values in row.values:
            prefix = hub_values.system_name.lower()
            values[f"{prefix}_buy"] = _csv_value(hub_values.buy)
            values[f"{prefix}_sell"] = _csv_value(hub_values.sell)
            values[f"{prefix}_hist"] = _csv_value(hub_values.history)
        writer.writerow(metadata | values)
    return stream.getvalue()
