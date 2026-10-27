"""Pure JSON, CSV, and Jinja Markdown renderers for hub-to-hub trade reports."""

import csv
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from io import StringIO
from typing import Any

from jinja2 import Environment, PackageLoader, StrictUndefined

from pfmsoft.eve_argus.helpers.currency import as_currency
from pfmsoft.eve_argus.helpers.markdown import format_markdown, markdown_cell
from pfmsoft.eve_argus.reports.hub_trades import (
    MAX_SNAPSHOT_SPREAD_SECONDS,
    REPORT_WIDE_FLAGS,
    HubTradeRow,
    HubTradesReport,
    SnapshotProvenance,
)
from pfmsoft.eve_argus.reports.station_trades import COMPETITION_SCOPE

MARKDOWN_TOP_ROWS = 100
"""Maximum ranked rows in the Markdown table; CSV and JSON keep every row."""

HUB_TRADES_CSV_COLUMNS = (
    "generated_at",
    "source_region_id",
    "source_system_name",
    "source_station_id",
    "source_station_name",
    "source_order_response_metadata_id",
    "source_orders_received_at",
    "source_orders_expiry_used",
    "source_orders_freshness",
    "destination_region_id",
    "destination_system_name",
    "destination_station_id",
    "destination_station_name",
    "destination_order_response_metadata_id",
    "destination_orders_received_at",
    "destination_orders_expiry_used",
    "destination_orders_freshness",
    "type_id",
    "type_name",
    "market_group_id",
    "market_path",
    "status",
    "rank",
    "flags",
    "is_best_match",
    "destination_match_count",
    "best_match_destination",
    "alternate_destinations",
    "competition_scope",
    "sales_tax_percent",
    "transport_per_m3",
    "min_profit",
    "include_market_group_ids",
    "exclude_market_group_ids",
    "m3_per_unit",
    "units",
    "total_m3",
    "best_sell_price",
    "last_sell_price",
    "average_sell_price",
    "best_buy_price",
    "last_buy_price",
    "average_buy_price",
    "source_available_units",
    "destination_demand_units",
    "source_order_count",
    "destination_order_count",
    "limit_reason",
    "purchase_cost",
    "gross_revenue",
    "sales_tax",
    "transport_cost",
    "net_profit",
    "net_margin_percent",
    "profit_per_m3",
)
_TOTAL_COLUMNS = (
    "units",
    "total_m3",
    "last_sell_price",
    "average_sell_price",
    "last_buy_price",
    "average_buy_price",
    "source_order_count",
    "destination_order_count",
    "purchase_cost",
    "gross_revenue",
    "sales_tax",
    "transport_cost",
    "net_profit",
    "net_margin_percent",
    "profit_per_m3",
)


def _plain(value: object) -> object:
    """Render Decimals as exact plain strings and booleans as lowercase words."""
    match value:
        case bool():
            return "true" if value else "false"
        case Decimal():
            return format(value, "f")
        case _:
            return value


def _jsonable(value: Any) -> Any:
    match value:
        case Decimal():
            return format(value, "f")
        case dict():
            return {str(key): _jsonable(item) for key, item in value.items()}
        case tuple() | list():
            return [_jsonable(item) for item in value]
        case _:
            return value


def _ids(values: tuple[int, ...]) -> str:
    return ";".join(str(value) for value in values)


def _snapshot(snapshot: SnapshotProvenance) -> dict[str, Any]:
    return {
        **asdict(snapshot.hub),
        "response_metadata_id": snapshot.response_metadata_id,
        "received_at": snapshot.received_at,
        "expires_at": snapshot.expires_at,
        "argus_expires_at": snapshot.argus_expires_at,
        "expiry_used": snapshot.expiry_used,
        "freshness": snapshot.freshness,
    }


def _sum_m3(rows: tuple[HubTradeRow, ...]) -> Decimal:
    return sum(
        (row.totals.total_m3 for row in rows if row.totals and row.totals.total_m3),
        Decimal(0),
    )


def _sum_profit(rows: tuple[HubTradeRow, ...]) -> Decimal:
    return sum((row.totals.net_profit for row in rows if row.totals), Decimal(0))


def hub_trades_payload(report: HubTradesReport) -> dict[str, Any]:
    """Return the JSON-ready payload for one source station."""
    options = report.options
    best = report.best_matches
    return _jsonable(
        {
            "schema_version": report.schema_version,
            "report": "hub-trades",
            "generated_at": report.generated_at,
            "source": _snapshot(report.source),
            "destinations": [_snapshot(item) for item in report.destinations],
            "snapshot_spread_seconds": report.snapshot_spread_seconds,
            "assumptions": {
                "competition_scope": COMPETITION_SCOPE,
                "sales_tax_percent": options.sales_tax_percent,
                "transport_per_m3": options.transport_per_m3,
                "min_profit": options.min_profit,
                "broker_fees_apply": False,
                "max_snapshot_spread_seconds": MAX_SNAPSHOT_SPREAD_SECONDS,
                "destination_walks_independent": True,
                "markdown_ranked_row_limit": MARKDOWN_TOP_ROWS,
            },
            "filters": {
                "include_market_group_ids": list(options.include_market_group_ids),
                "exclude_market_group_ids": list(options.exclude_market_group_ids),
                "filtered_out_count": report.filtered_out_count,
            },
            "warnings": report.warnings,
            "summary": {
                "row_count": len(report.records),
                "ranked_count": len(report.ranked),
                "status_counts": report.status_counts,
                "no_overlap_count": report.no_overlap_count,
                "best_match_item_count": len(best),
                "multi_destination_item_count": len(report.multi_destination_items),
                "best_match_total_net_profit": _sum_profit(best),
                "best_match_total_m3": _sum_m3(best),
            },
            "records": [asdict(row) for row in report.records],
        }
    )


def render_hub_trades_json(report: HubTradesReport) -> str:
    """Render the report as indented JSON with exact decimal strings."""
    return json.dumps(hub_trades_payload(report), indent=2) + "\n"


def _snapshot_values(prefix: str, snapshot: SnapshotProvenance) -> dict[str, object]:
    hub = snapshot.hub
    return {
        f"{prefix}_region_id": hub.region_id,
        f"{prefix}_system_name": hub.system_name,
        f"{prefix}_station_id": hub.station_id,
        f"{prefix}_station_name": hub.station_name,
        f"{prefix}_order_response_metadata_id": snapshot.response_metadata_id,
        f"{prefix}_orders_received_at": snapshot.received_at,
        f"{prefix}_orders_expiry_used": snapshot.expiry_used,
        f"{prefix}_orders_freshness": snapshot.freshness,
    }


def _row_values(
    report: HubTradesReport, row: HubTradeRow, destination: SnapshotProvenance
) -> dict[str, object]:
    options = report.options
    totals = row.totals
    return {
        "generated_at": report.generated_at,
        **_snapshot_values("source", report.source),
        **_snapshot_values("destination", destination),
        "type_id": row.type_id,
        "type_name": row.type_name,
        "market_group_id": row.market_group_id,
        "market_path": "/".join(row.market_path_names),
        "status": row.status,
        "rank": row.rank,
        "flags": ";".join(row.flags),
        "is_best_match": row.is_best_match,
        "destination_match_count": row.destination_match_count,
        "best_match_destination": row.best_match_destination,
        "alternate_destinations": ";".join(row.alternate_destinations),
        "competition_scope": COMPETITION_SCOPE,
        "sales_tax_percent": options.sales_tax_percent,
        "transport_per_m3": options.transport_per_m3,
        "min_profit": options.min_profit,
        "include_market_group_ids": _ids(options.include_market_group_ids),
        "exclude_market_group_ids": _ids(options.exclude_market_group_ids),
        "m3_per_unit": row.m3_per_unit,
        "best_sell_price": row.best_sell_price,
        "best_buy_price": row.best_buy_price,
        "source_available_units": row.source_available_units,
        "destination_demand_units": row.destination_demand_units,
        "limit_reason": row.limit_reason,
        **{
            name: None if totals is None else getattr(totals, name)
            for name in _TOTAL_COLUMNS
        },
    }


def _destinations(report: HubTradesReport) -> dict[int, SnapshotProvenance]:
    return {item.hub.station_id: item for item in report.destinations}


def render_hub_trades_csv(report: HubTradesReport) -> str:
    """Render one row per kept destination and type with stable columns."""
    destinations = _destinations(report)
    stream = StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=HUB_TRADES_CSV_COLUMNS, lineterminator="\n"
    )
    writer.writeheader()
    for row in report.records:
        values = _row_values(report, row, destinations[row.destination_station_id])
        writer.writerow({name: _plain(value) for name, value in values.items()})
    return stream.getvalue()


def _isk(value: Decimal | None) -> str:
    return "" if value is None else f"{as_currency(value):,.2f}"


def _percent(value: Decimal | None) -> str:
    return "" if value is None else f"{value:,.2f}%"


def _number(value: Decimal | int | None) -> str:
    """Format a quantity or option without trailing zeros or exponents."""
    match value:
        case None:
            return ""
        case int():
            return f"{value:,}"
        case _:
            return format(value.normalize(), ",f") if value else "0"


@dataclass(slots=True, kw_only=True, frozen=True)
class _MarkdownRow:
    """Display strings for one ranked row; calculations stay in the collector."""

    rank: int
    best: str
    item: str
    destination: str
    units: str
    m3_per_unit: str
    total_m3: str
    buy_from: str
    sell_to: str
    purchase_cost: str
    sales_tax: str
    transport: str
    net_profit: str
    margin: str
    profit_per_m3: str
    limit: str
    flags: str


@dataclass(slots=True, kw_only=True, frozen=True)
class _DestinationSummary:
    destination: str
    freshness: str
    ranked: int
    best_matches: int
    best_match_profit: str
    best_match_m3: str


def _markdown_row(row: HubTradeRow) -> _MarkdownRow:
    totals = row.totals
    if totals is None or row.rank is None:
        raise ValueError(f"Ranked type {row.type_id} has no totals or rank.")
    others = len(row.alternate_destinations) if row.is_best_match else 0
    return _MarkdownRow(
        rank=row.rank,
        best="★" if row.is_best_match else "",
        item=f"{markdown_cell(row.type_name)} (`{row.type_id}`)",
        destination=row.destination_system_name + (f" (+{others})" if others else ""),
        units=_number(totals.units),
        m3_per_unit=_number(row.m3_per_unit),
        total_m3=_number(totals.total_m3),
        buy_from=f"{_isk(row.best_sell_price)} / {_isk(totals.last_sell_price)}",
        sell_to=f"{_isk(row.best_buy_price)} / {_isk(totals.last_buy_price)}",
        purchase_cost=_isk(totals.purchase_cost),
        sales_tax=_isk(totals.sales_tax),
        transport=_isk(totals.transport_cost),
        net_profit=_isk(totals.net_profit),
        margin=_percent(totals.net_margin_percent),
        profit_per_m3=_isk(totals.profit_per_m3),
        limit=row.limit_reason or "",
        flags=markdown_cell(
            ", ".join(flag for flag in row.flags if flag not in REPORT_WIDE_FLAGS)
        ),
    )


def _destination_summaries(report: HubTradesReport) -> list[_DestinationSummary]:
    summaries = []
    for destination in report.destinations:
        station_id = destination.hub.station_id
        ranked = tuple(
            row for row in report.ranked if row.destination_station_id == station_id
        )
        best = tuple(row for row in ranked if row.is_best_match)
        summaries.append(
            _DestinationSummary(
                destination=destination.hub.system_name,
                freshness=destination.freshness,
                ranked=len(ranked),
                best_matches=len(best),
                best_match_profit=_isk(_sum_profit(best)),
                best_match_m3=_number(_sum_m3(best)),
            )
        )
    return summaries


def _multi_destination_lines(report: HubTradesReport) -> list[str]:
    lines = []
    for item in report.multi_destination_items:
        best = item.best
        if best.totals is None:
            raise ValueError(f"Best match {best.type_id} has no totals.")
        alternates = ", ".join(
            f"{row.destination_system_name} "
            f"{_isk(row.totals.net_profit if row.totals else None)}"
            for row in item.alternates
        )
        m3 = _number(best.totals.total_m3) or "unknown"
        lines.append(
            f"{markdown_cell(best.type_name)} (`{best.type_id}`): best "
            f"{best.destination_system_name} {_isk(best.totals.net_profit)} ISK "
            f"({m3} m³); also {alternates}"
        )
    return lines


def render_hub_trades_markdown(report: HubTradesReport) -> str:
    """Render the summary, ranked trades, multi-destination items, and notes."""
    environment = Environment(
        loader=PackageLoader("pfmsoft.eve_argus.templates", "hub_trades"),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    ranked = report.ranked
    best = report.best_matches
    rendered = environment.get_template(
        "report.md.jinja2", globals={"cell": markdown_cell, "number": _number}
    ).render(
        report=report,
        source=report.source,
        options=report.options,
        destination_summaries=_destination_summaries(report),
        best_match_count=len(best),
        best_match_profit=_isk(_sum_profit(best)),
        best_match_m3=_number(_sum_m3(best)),
        rows=[_markdown_row(row) for row in ranked[:MARKDOWN_TOP_ROWS]],
        ranked_total=len(ranked),
        multi_destination_lines=_multi_destination_lines(report),
        unranked_counts={
            status: count
            for status, count in report.status_counts.items()
            if status != "ranked"
        },
        spread_minutes=report.snapshot_spread_seconds // 60,
        max_spread_minutes=MAX_SNAPSHOT_SPREAD_SECONDS // 60,
        include_ids=", ".join(map(str, report.options.include_market_group_ids)),
        exclude_ids=", ".join(map(str, report.options.exclude_market_group_ids)),
    )
    return format_markdown(rendered)
