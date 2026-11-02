"""Pure CSV and JSON serializers for region and system price summaries."""

import csv
import json
from dataclasses import asdict, fields
from decimal import Decimal
from io import StringIO

from pfmsoft.eve_argus.reports.market_hub_prices import PriceSummaryMetrics
from pfmsoft.eve_argus.reports.price_summaries import (
    PriceSummariesReport,
    PriceSummaryRow,
)

_METADATA_COLUMNS = tuple(
    field.name for field in fields(PriceSummariesReport) if field.name != "records"
)
_ROW_COLUMNS = tuple(
    field.name
    for field in fields(PriceSummaryRow)
    if field.name not in ("buy_summary", "sell_summary")
)
_METRIC_COLUMNS = tuple(field.name for field in fields(PriceSummaryMetrics))
CSV_COLUMNS = (
    *_METADATA_COLUMNS,
    *_ROW_COLUMNS,
    "has_buy_summary",
    "has_sell_summary",
    *(f"{side}_{metric}" for side in ("buy", "sell") for metric in _METRIC_COLUMNS),
)


def _json_decimal(value: object) -> str:
    """Serialize exact monetary values as plain decimal strings."""
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(f"Cannot serialize {type(value).__name__} as JSON.")


def render_price_summaries_json(report: PriceSummariesReport) -> str:
    """Render metadata and ordered records, preserving exact prices and nulls."""
    return (
        json.dumps(asdict(report), default=_json_decimal, ensure_ascii=False, indent=2)
        + "\n"
    )


def render_price_summaries_csv(report: PriceSummariesReport) -> str:
    """Render one LF-terminated CSV row per type with empty missing-side cells."""
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
        for side, summary in (("buy", row.buy_summary), ("sell", row.sell_summary)):
            values[f"has_{side}_summary"] = summary is not None
            if summary is not None:
                for name in _METRIC_COLUMNS:
                    value = getattr(summary, name)
                    values[f"{side}_{name}"] = (
                        format(value, "f") if isinstance(value, Decimal) else value
                    )
        writer.writerow(metadata | values)
    return stream.getvalue()
