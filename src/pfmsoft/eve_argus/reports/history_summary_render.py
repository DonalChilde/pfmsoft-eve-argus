"""Pure CSV and JSON serializers for regional market-history summaries."""

import csv
import json
from dataclasses import asdict, fields
from decimal import Decimal
from io import StringIO

from pfmsoft.eve_argus.helpers.currency import as_currency
from pfmsoft.eve_argus.reports.history_summary import (
    HistorySummaryReport,
    HistorySummaryRow,
)

_PRICE_FIELDS = ("highest_price", "average_price", "lowest_price")
_METADATA_COLUMNS = tuple(
    field.name for field in fields(HistorySummaryReport) if field.name != "records"
)
_ROW_COLUMNS = tuple(field.name for field in fields(HistorySummaryRow))
CSV_COLUMNS = (*_METADATA_COLUMNS, *_ROW_COLUMNS)


def _json_decimal(value: object) -> str:
    """Serialize exact price/volume decimals as plain decimal strings."""
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(f"Cannot serialize {type(value).__name__} as JSON.")


def _format_price(value: Decimal | None) -> str | None:
    """Render a nullable price as currency with two decimal places."""
    return format(as_currency(value), "f") if value is not None else None


def render_history_summary_json(report: HistorySummaryReport) -> str:
    """Render a schema-versioned report with currency-formatted prices."""
    report_data = asdict(report)
    for row in report_data["records"]:
        for field in _PRICE_FIELDS:
            row[field] = _format_price(row[field])
    return (
        json.dumps(report_data, default=_json_decimal, ensure_ascii=False, indent=2)
        + "\n"
    )


def render_history_summary_csv(report: HistorySummaryReport) -> str:
    """Render one LF-terminated CSV row per type with metadata repeated."""
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    metadata = {name: getattr(report, name) for name in _METADATA_COLUMNS}
    for row in report.records:
        values = {name: getattr(row, name) for name in _ROW_COLUMNS}
        values["market_path_ids"] = (
            "/".join(str(part) for part in row.market_path_ids)
            if row.market_path_ids is not None
            else None
        )
        values["market_path_names"] = (
            "/".join(row.market_path_names)
            if row.market_path_names is not None
            else None
        )
        for key in _PRICE_FIELDS:
            values[key] = _format_price(values[key])
        value = values["average_daily_volume"]
        if isinstance(value, Decimal):
            values["average_daily_volume"] = format(value, "f")
        writer.writerow(metadata | values)
    return stream.getvalue()
