"""Pure JSON, CSV, and Jinja Markdown renderers for station-trades reports."""

import csv
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from io import StringIO
from typing import Any

from jinja2 import Environment, PackageLoader, StrictUndefined

from pfmsoft.eve_argus.dynamic.order_summary import FILTER_FACTOR_DEFAULT
from pfmsoft.eve_argus.helpers.currency import as_currency
from pfmsoft.eve_argus.helpers.markdown import format_markdown, markdown_cell
from pfmsoft.eve_argus.reports.station_trades import (
    COMPETITION_SCOPE,
    HISTORY_DAYS,
    HISTORY_STALE_DAYS,
    MARKET_TICK_SIGNIFICANT_FIGURES,
    MINIMUM_MARKET_TICK,
    PRICE_POLICY,
    REPORT_WIDE_FLAGS,
    SideSummary,
    StationTradeRow,
    StationTradesReport,
)

MARKDOWN_TOP_ROWS = 100
"""Maximum ranked rows in Markdown tables; CSV and JSON keep every row."""

STATION_TRADES_CSV_COLUMNS = (
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
    "include_market_group_ids",
    "exclude_market_group_ids",
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
_ECONOMICS_COLUMNS = STATION_TRADES_CSV_COLUMNS[
    STATION_TRADES_CSV_COLUMNS.index("gross_spread_per_unit") :
]


def _plain(value: object) -> object:
    """Render Decimals as exact plain strings; leave other values unchanged."""
    return format(value, "f") if isinstance(value, Decimal) else value


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


def station_trades_payload(report: StationTradesReport) -> dict[str, Any]:
    """Build the JSON document, preserving exact Decimal strings and nulls."""
    window = report.history_window
    options = report.options
    return _jsonable(
        {
            "schema_version": report.schema_version,
            "report": "station-trades",
            "scope": asdict(report.hub),
            "generated_at": report.generated_at,
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
                "window_start_date": None if window is None else window.oldest_date,
                "window_end_date": None if window is None else window.newest_date,
                "stale_after_days": HISTORY_STALE_DAYS,
                "generation_date_utc": report.generated_at[:10],
            },
            "assumptions": {
                "price_policy": PRICE_POLICY,
                "minimum_market_tick_isk": MINIMUM_MARKET_TICK,
                "market_tick_significant_figures": MARKET_TICK_SIGNIFICANT_FIGURES,
                "competition_scope": COMPETITION_SCOPE,
                "participation_percent": options.participation_percent,
                "acquisition_broker_fee_percent": (
                    options.acquisition_broker_fee_percent
                ),
                "sale_broker_fee_percent": options.sale_broker_fee_percent,
                "sales_tax_percent": options.sales_tax_percent,
                "summary_filter_factor": FILTER_FACTOR_DEFAULT,
                "markdown_ranked_row_limit": MARKDOWN_TOP_ROWS,
                "capital_constraints_modeled": False,
                "repricing_costs_modeled": False,
                "history_is_regional_not_station_specific": True,
            },
            "filters": {
                "include_market_group_ids": list(options.include_market_group_ids),
                "exclude_market_group_ids": list(options.exclude_market_group_ids),
                "filtered_out_count": report.filtered_out_count,
            },
            "warnings": report.warnings,
            "summary": {
                "candidate_count": len(report.records),
                "ranked_count": len(report.ranked),
                "unranked_count": len(report.records) - len(report.ranked),
                "status_counts": report.status_counts,
            },
            "records": [asdict(row) for row in report.records],
        }
    )


def render_station_trades_json(report: StationTradesReport) -> str:
    """Render one station report as indented JSON."""
    return (
        json.dumps(station_trades_payload(report), ensure_ascii=False, indent=2) + "\n"
    )


def _side_values(prefix: str, side: SideSummary | None) -> dict[str, object]:
    return {
        f"five_percent_{prefix}_price": None if side is None else side.five_price,
        f"five_percent_{prefix}_depth_order_count": (
            None if side is None else side.five_orders
        ),
        f"five_percent_{prefix}_depth_quantity": None
        if side is None
        else side.five_items,
    }


def _row_values(report: StationTradesReport, row: StationTradeRow) -> dict[str, object]:
    hub, options, history, window = (
        report.hub,
        report.options,
        row.history,
        report.history_window,
    )
    values: dict[str, object] = {
        "generated_at": report.generated_at,
        "order_response_metadata_id": report.order_response_metadata_id,
        "orders_received_at": report.orders_received_at,
        "orders_expires_at": report.orders_expires_at,
        "orders_argus_expires_at": report.orders_argus_expires_at,
        "orders_expiry_used": report.orders_expiry_used,
        "orders_freshness": report.orders_freshness,
        "region_id": hub.region_id,
        "region_name": hub.region_name,
        "system_id": hub.system_id,
        "system_name": hub.system_name,
        "station_id": hub.station_id,
        "station_name": hub.station_name,
        "type_id": row.type_id,
        "type_name": row.type_name,
        "market_group_id": row.market_group_id,
        "market_path": "/".join(row.market_path_names),
        "status": row.status,
        "rank": row.rank,
        "flags": ";".join(row.flags),
        "missing_data": ";".join(row.missing_data),
        "competition_scope": COMPETITION_SCOPE,
        "participation_percent": options.participation_percent,
        "history_window_days": HISTORY_DAYS,
        "acquisition_broker_fee_percent": options.acquisition_broker_fee_percent,
        "sale_broker_fee_percent": options.sale_broker_fee_percent,
        "sales_tax_percent": options.sales_tax_percent,
        "include_market_group_ids": _ids(options.include_market_group_ids),
        "exclude_market_group_ids": _ids(options.exclude_market_group_ids),
        "summary_filter_factor": FILTER_FACTOR_DEFAULT,
        "price_policy": PRICE_POLICY,
        "best_station_buy_price": row.best_station_buy_price,
        "best_station_sell_price": row.best_station_sell_price,
        "proposed_buy_price": row.proposed_buy_price,
        "proposed_sell_price": row.proposed_sell_price,
        "station_buy_remaining_quantity": row.station_buy_remaining_quantity,
        "station_sell_remaining_quantity": row.station_sell_remaining_quantity,
        "station_buy_order_count": row.station_buy_order_count,
        "station_sell_order_count": row.station_sell_order_count,
        **_side_values("buy", row.five_percent_buy),
        **_side_values("sell", row.five_percent_sell),
        "history_received_at": history.received_at,
        "history_expires_at": history.expires_at,
        "history_argus_expires_at": history.argus_expires_at,
        "history_freshness": history.freshness,
        "history_window_start_date": None if window is None else window.oldest_date,
        "history_window_end_date": None if window is None else window.newest_date,
        "history_oldest_date_used": history.oldest_date_used,
        "history_newest_date_used": history.newest_date_used,
        "history_missing_days": history.missing_days,
        "regional_history_average_price": history.average_price,
        "regional_average_daily_volume": history.average_daily_volume,
        "regional_average_daily_order_count": history.average_daily_order_count,
        "proposed_buy_deviation_percent": row.proposed_buy_deviation_percent,
        "proposed_sell_deviation_percent": row.proposed_sell_deviation_percent,
    }
    economics = row.economics
    for name in _ECONOMICS_COLUMNS:
        values[name] = None if economics is None else getattr(economics, name)
    return values


def render_station_trades_csv(report: StationTradesReport) -> str:
    """Render every candidate as one LF-terminated CSV record."""
    stream = StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=STATION_TRADES_CSV_COLUMNS, lineterminator="\n"
    )
    writer.writeheader()
    for row in report.records:
        writer.writerow(
            {name: _plain(value) for name, value in _row_values(report, row).items()}
        )
    return stream.getvalue()


@dataclass(slots=True, kw_only=True, frozen=True)
class _MarkdownRow:
    """Display strings for one ranked row; calculations stay in the collector."""

    rank: int
    item: str
    market_path: str
    best_buy: str
    best_sell: str
    proposed_buy: str
    proposed_sell: str
    net_profit: str
    margin: str
    history_average: str
    daily_volume: str
    daily_units: str
    daily_profit: str
    capital: str
    station_depth: str
    history_coverage: str
    buy_deviation: str
    sell_deviation: str
    flags: str
    acquisition_fee: str
    sale_fee: str
    sales_tax: str
    daily_acquisition_fee: str
    daily_sale_fee: str
    daily_sales_tax: str


def _isk(value: Decimal | None) -> str:
    return "" if value is None else f"{as_currency(value):,.2f}"


def _percent(value: Decimal | None) -> str:
    return "" if value is None else f"{value:,.2f}%"


def _number(value: Decimal | None) -> str:
    """Format a quantity or option without trailing zeros or exponents."""
    if value is None:
        return ""
    return format(value.normalize(), ",f") if value else "0"


def _depth(row: StationTradeRow) -> str:
    text = (
        f"buy {row.station_buy_order_count}/{row.station_buy_remaining_quantity:,}; "
        f"sell {row.station_sell_order_count}/{row.station_sell_remaining_quantity:,}"
    )
    if row.five_percent_buy and row.five_percent_sell:
        text += (
            f"; 5% buy {row.five_percent_buy.five_orders}/"
            f"{row.five_percent_buy.five_items:,}, sell "
            f"{row.five_percent_sell.five_orders}/"
            f"{row.five_percent_sell.five_items:,}"
        )
    return text


def _coverage(row: StationTradeRow) -> str:
    history = row.history
    if history.newest_date_used is None:
        return "missing"
    return (
        f"{history.oldest_date_used} to {history.newest_date_used}; "
        f"{history.missing_days} missing"
    )


def _markdown_row(row: StationTradeRow) -> _MarkdownRow:
    economics = row.economics
    if economics is None or row.rank is None:
        raise ValueError(f"Ranked type {row.type_id} has no economics or rank.")
    return _MarkdownRow(
        rank=row.rank,
        item=f"{markdown_cell(row.type_name)} (`{row.type_id}`)",
        market_path=markdown_cell(" > ".join(row.market_path_names)),
        best_buy=_isk(row.best_station_buy_price),
        best_sell=_isk(row.best_station_sell_price),
        proposed_buy=_isk(row.proposed_buy_price),
        proposed_sell=_isk(row.proposed_sell_price),
        net_profit=_isk(economics.net_profit_per_unit),
        margin=_percent(economics.net_margin_percent),
        history_average=_isk(row.history.average_price),
        daily_volume=_number(row.history.average_daily_volume),
        daily_units=_number(economics.estimated_daily_units),
        daily_profit=_isk(economics.estimated_daily_net_profit),
        capital=_isk(economics.modeled_acquisition_capital),
        station_depth=_depth(row),
        history_coverage=_coverage(row),
        buy_deviation=_percent(row.proposed_buy_deviation_percent),
        sell_deviation=_percent(row.proposed_sell_deviation_percent),
        flags=markdown_cell(
            ", ".join(flag for flag in row.flags if flag not in REPORT_WIDE_FLAGS)
        ),
        acquisition_fee=_isk(economics.acquisition_broker_fee_per_unit),
        sale_fee=_isk(economics.sale_broker_fee_per_unit),
        sales_tax=_isk(economics.sales_tax_per_unit),
        daily_acquisition_fee=_isk(economics.daily_acquisition_broker_fee),
        daily_sale_fee=_isk(economics.daily_sale_broker_fee),
        daily_sales_tax=_isk(economics.daily_sales_tax),
    )


def render_station_trades_markdown(report: StationTradesReport) -> str:
    """Render ranked opportunities, fee details, warnings, and definitions."""
    environment = Environment(
        loader=PackageLoader("pfmsoft.eve_argus.templates", "station_trades"),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    ranked = report.ranked
    rendered = environment.get_template(
        "report.md.jinja2", globals={"cell": markdown_cell, "number": _number}
    ).render(
        report=report,
        hub=report.hub,
        options=report.options,
        rows=[_markdown_row(row) for row in ranked[:MARKDOWN_TOP_ROWS]],
        ranked_total=len(ranked),
        unranked_counts={
            status: count
            for status, count in report.status_counts.items()
            if status != "ranked"
        },
        history_days=HISTORY_DAYS,
        stale_days=HISTORY_STALE_DAYS,
        minimum_tick=MINIMUM_MARKET_TICK,
        filter_factor=FILTER_FACTOR_DEFAULT,
        include_ids=", ".join(map(str, report.options.include_market_group_ids)),
        exclude_ids=", ".join(map(str, report.options.exclude_market_group_ids)),
    )
    return format_markdown(rendered)
