"""Collect and render a standalone PI operations report."""

import json
from dataclasses import dataclass, replace
from decimal import Decimal

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from pfmsoft.eve_argus.pi.models import Material
from pfmsoft.eve_argus.reports.history_summary import HistorySummaryReport
from pfmsoft.eve_argus.reports.history_summary_render import render_history_summary_json
from pfmsoft.eve_argus.reports.price_summaries import (
    PriceSummariesReport,
    PriceSummaryRow,
)
from pfmsoft.eve_argus.reports.price_summaries_render import render_price_summaries_json


@dataclass(frozen=True, slots=True, kw_only=True)
class PiOperationsReport:
    """Canonical PI recipes and the three scoped market summaries."""

    materials: tuple[Material, ...]
    jita: PriceSummariesReport
    forge: PriceSummariesReport
    history: HistorySummaryReport


def _include_missing_prices(
    prices: PriceSummariesReport, history: HistorySummaryReport
) -> PriceSummariesReport:
    """Keep every catalog type visible even when both order sides are absent."""
    priced = {row.type_id: row for row in prices.records}
    return replace(
        prices,
        records=tuple(
            priced.get(row.type_id)
            or PriceSummaryRow(
                type_id=row.type_id,
                type_name=row.type_name,
                market_group_id=row.market_group_id,
                market_group_name=row.market_group_name,
                market_path_ids=row.market_path_ids,
                market_path_names=row.market_path_names,
                buy_summary=None,
                sell_summary=None,
            )
            for row in history.records
        ),
    )


def _decimal(value: Decimal | None) -> str | None:
    """Serialize a quote without converting it to a float."""
    return None if value is None else format(value, "f")


def render_pi_operations(report: PiOperationsReport) -> str:
    """Render one self-contained, autoescaped HTML document."""
    jita = {row.type_id: row for row in report.jita.records}
    history = {row.type_id: row for row in report.history.records}
    materials = {}
    for material in report.materials:
        orders = jita.get(material.type_id)
        buy = orders.buy_summary if orders else None
        sell = orders.sell_summary if orders else None
        historical = history[material.type_id]
        materials[material.type_id] = {
            "name": material.name,
            "tier": int(material.tier),
            "taxBase": str(material.taxable_base),
            "volume": str(material.volume),
            "output": material.output_quantity,
            "inputs": [(item.type_id, item.quantity) for item in material.inputs],
            "prices": {
                "Jita Buy 5%": _decimal(buy.five_price if buy else None),
                "Jita Sell 5%": _decimal(sell.five_price if sell else None),
                "The Forge Avg": _decimal(
                    historical.average_price
                    if historical.average_daily_volume
                    else None
                ),
            },
            "history": {
                "oldest": historical.oldest_date,
                "newest": historical.newest_date,
                "stale": historical.is_stale,
            },
        }
    reports = {
        key: json.loads(
            render_price_summaries_json(_include_missing_prices(book, report.history))
        )
        for key, book in (("jita", report.jita), ("forge-prices", report.forge))
    }
    reports["forge-history"] = json.loads(render_history_summary_json(report.history))
    environment = Environment(
        loader=PackageLoader("pfmsoft.eve_argus", "templates/pi_operations"),
        autoescape=select_autoescape(("html",)),
        undefined=StrictUndefined,
    )
    environment.policies["json.dumps_kwargs"] = {"sort_keys": False}
    return environment.get_template("report.html").render(
        materials=materials, reports=reports
    )
