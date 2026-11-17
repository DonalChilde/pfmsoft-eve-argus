"""Synthetic acceptance tests kept alongside the isolated industry proof."""

import csv
import io
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

import pytest
from industry_proof import (
    Blueprint,
    Item,
    Material,
    Original,
    Planner,
    Purchase,
    Source,
    build_report,
    known_sum,
    rounded_attempts,
)
from proof_inputs import demo_inputs
from proof_render import (
    Section,
    profit_opportunities,
    render_csv,
    render_html,
    render_markdown,
    render_pages,
    report_pages,
    sections,
    write_reports,
)
from run_report import main

from pfmsoft.eve_argus.helpers.markdown import format_markdown

D = Decimal


@pytest.mark.parametrize(
    ("age", "status"),
    (
        (timedelta(days=7), "fresh"),
        (timedelta(days=7, microseconds=1), "stale"),
        (timedelta(days=6), "fresh"),
    ),
)
def test_history_receipt_staleness(age: timedelta, status: str) -> None:
    """Only receipts strictly older than the configured age are stale."""
    received = datetime(2026, 11, 1, tzinfo=UTC)
    source = Source(
        label="History",
        reference="fixture",
        received_at=received.isoformat(),
        expires_at=received.isoformat(),
        history_stale_days=7,
    )
    assert source.freshness(now=received + age) == status
    assert (
        replace(source, history_stale_days=3).freshness(
            now=received + timedelta(days=4)
        )
        == "stale"
    )


@pytest.mark.parametrize("activity", ("copying", "manufacturing", "invention"))
def test_zero_activity_time_is_named_incomplete(activity: str) -> None:
    """Malformed source timings cannot abort the entire report."""
    data = demo_inputs()
    if activity == "invention":
        data.inventions = tuple(replace(r, seconds=0) for r in data.inventions)
        product = 200
    else:
        field = f"{activity}_seconds"
        data.blueprints[1100] = replace(data.blueprints[1100], **{field: 0})
        product = 100
    report = build_report(data, product_ids=(product,))
    assert all(p.status == "incomplete" for p in report.plans)
    assert any(
        f"Invalid {activity} duration" in warning
        and "Synthetic T1 assembly Blueprint (1100)" in warning
        for warning in report.plans[0].warnings
    )


@pytest.mark.parametrize("daily_sales", (D("12.5"), D(0), None))
def test_sales_data_daily_traded_units(daily_sales: Decimal | None) -> None:
    """Show regional daily volume for every basis, retaining zero and unknown."""
    data = demo_inputs()
    key = (60003760, 100)
    data.markets[key] = replace(data.markets[key], daily_sales=daily_sales)
    report = build_report(data, product_ids=(100,))
    plan = report.plans[0]
    sale = next(s for s in sections(report) if s.anchor == plan.anchor).tables[0]
    assert sale.headings[-2:] == ("Avg traded units/day", "Status")
    expected = "Unavailable" if daily_sales is None else f"{daily_sales:,.2f}"
    assert all(row[-2] == expected for row in sale.rows[:3])
    assert all(
        row[-1] == outcome.status
        for row, outcome in zip(sale.rows, plan.outcomes, strict=True)
    )


def test_diagnostics_include_names_and_ids() -> None:
    """Keep human identity and machine identity together across report warnings."""
    data = demo_inputs()
    del data.input_prices[1]
    del data.adjusted_prices[1]
    plan = build_report(data, product_ids=(100,)).plans[0]
    assert "Missing Jita sell 5% price: Synthetic mineral (1)." in plan.warnings
    assert any(
        "Missing adjusted price for Synthetic mineral (1)" in warning
        and "Synthetic T1 assembly Blueprint (1100)" in warning
        for warning in plan.warnings
    )
    data.originals = ()
    missing = build_report(data, product_ids=(100,)).plans[0]
    assert "Missing owned BPO for Synthetic T1 assembly (100)." in missing.warnings
    assert Planner(data).identity(999999) == "UNKNOWN (999999)"
    report = build_report(data, product_ids=(100,))
    assert "Synthetic T1 assembly (100)" in render_html(report)


def test_profit_opportunities_threshold_order_and_sales_data() -> None:
    """Filter history returns inclusively and reuse each scenario's sales data."""
    report = build_report(demo_inputs(), product_ids=(100,))
    plan = report.plans[0]
    original = plan.outcomes[0]
    plan.outcomes = [
        replace(original, basis="buy_5pct", return_pct=D(100)),
        replace(
            original,
            basis="sell_5pct",
            return_pct=D(100),
            status="indicative; insufficient 5% depth",
        ),
        replace(
            original,
            basis="history_average",
            return_pct=D("30.5"),
            status="regional proxy; no fill guarantee",
        ),
        replace(plan.outcomes[3], basis="history_average", return_pct=D(20)),
        replace(plan.outcomes[4], basis="history_average", return_pct=D("19.999")),
        *(replace(o, return_pct=None) for o in plan.outcomes[5:]),
    ]
    report.plans[1].outcomes = [
        replace(o, return_pct=None) for o in report.plans[1].outcomes
    ]
    detail = sections(report)
    opportunities = next(s for s in detail if s.anchor == "profit-opportunities")
    assert opportunities.title == "Profit Opportunities"
    assert opportunities.level == 2
    assert detail.index(opportunities) < next(
        i for i, s in enumerate(detail) if s.anchor == "item-100"
    )
    opportunity_table = opportunities.tables[0]
    sales = next(s for s in detail if s.anchor == plan.anchor).tables[0]
    assert opportunity_table.headings == (
        "Product",
        "Strategy",
        "Hub",
        "Avg traded Units/day",
        "Unit cost ISK",
        "History avg Price/unit",
        "Sell 5% Price/unit",
        "5% depth",
        *sales.headings[3:9],
        "Status",
    )
    assert opportunity_table.rows == (
        (
            report.data.items[100].name,
            plan.strategy,
            sales.rows[2][0],
            "15.00",
            f"{plan.unit_cost:,.2f}",
            sales.rows[2][2],
            "1,000.00",
            "2000",
            *sales.rows[2][3:9],
            "",
        ),
        (
            report.data.items[100].name,
            plan.strategy,
            sales.rows[3][0],
            "15.00",
            f"{plan.unit_cost:,.2f}",
            sales.rows[3][2],
            "1,000.00",
            "2000",
            *sales.rows[3][3:9],
            "",
        ),
    )
    for render in (render_markdown, render_html):
        assert "Profit Opportunities" in render(report)
    del report.data.markets[60003760, 100]
    updated = next(s for s in sections(report) if s.anchor == "profit-opportunities")
    assert updated.tables[0].rows[0][3] == "Unavailable"
    assert updated.tables[0].rows[0][6] == "Unavailable"
    assert updated.tables[0].rows[0][7] == "Unavailable"
    plan.outcomes = [replace(o, return_pct=D("19.999")) for o in plan.outcomes]
    empty = next(s for s in sections(report) if s.anchor == "profit-opportunities")
    assert not empty.tables[0].rows
    assert "No scenarios offer at least 20% return." in empty.paragraphs


@pytest.mark.parametrize(
    ("sell_price", "status"),
    (
        (D("799.999"), "Sell 5% price below history average"),
        (D(800), ""),
        (D(801), ""),
        (None, ""),
    ),
)
def test_profit_opportunities_sell_price_warning(
    *, sell_price: Decimal | None, status: str
) -> None:
    """Warn only when the unrounded sell price is below the history price."""
    report = build_report(demo_inputs(), product_ids=(100,))
    plan = report.plans[0]
    outcome = next(o for o in plan.outcomes if o.basis == "history_average")
    plan.outcomes = [replace(outcome, price=D(800), return_pct=D(20))]
    report.plans[1].outcomes = []
    key = (outcome.station_id, plan.type_id)
    report.data.markets[key] = replace(report.data.markets[key], sell=sell_price)
    opportunity = profit_opportunities(report)
    assert opportunity.tables[0].rows[0][-1] == status


@pytest.mark.parametrize("missing", (False, True))
def test_material_inputs_volume_and_totals(missing: bool) -> None:
    """Total displayed material rows, retaining unknown volume and valuation."""
    data = demo_inputs()
    data.items[1] = replace(data.items[1], volume=D("0.015"))
    data.items[10] = replace(data.items[10], volume=D(2))
    if missing:
        data.items[1] = replace(data.items[1], volume=None)
        del data.input_prices[1]
    report = build_report(data, product_ids=(100,))
    plan = report.plans[0]
    inputs = next(s for s in sections(report) if s.anchor == f"{plan.anchor}-inputs")
    material_table = inputs.tables[0]
    assert material_table.headings[2:4] == ("Quantity", "m3")
    total_volume = D(0)
    total_cost = D(0)
    for row, material in zip(
        material_table.rows[:-1],
        (m for j in plan.jobs for m in j.inputs),
        strict=True,
    ):
        volume = data.items[material.type_id].volume
        assert row[3] == (
            "Unavailable" if volume is None else f"{volume * material.quantity:,.2f}"
        )
        if volume is not None:
            total_volume += volume * material.quantity
        if not missing:
            total_cost += data.input_prices[material.type_id] * material.quantity
    expected_volume = "Unavailable" if missing else f"{total_volume:,.2f}"
    expected_cost = "Unavailable" if missing else f"{total_cost:,.2f}"
    assert material_table.rows[-1] == (
        "Total",
        "",
        "",
        expected_volume,
        "",
        "",
        expected_cost,
    )
    assert inputs.paragraphs == (
        f"Total m3: {expected_volume}. Total Cost: {expected_cost} ISK.",
    )
    for render in (render_markdown, render_html):
        assert inputs.paragraphs[0] in render(report)
        assert (
            "Quantities are rounded per actual manufacturing job after ME."
            not in render(report)
        )


def test_sale_table_splits_batch_tax_and_broker_fee() -> None:
    """Display separate batch charges, including zero and unavailable fees."""
    data = demo_inputs()
    data.markets.pop((60008494, 100))
    report = build_report(data, product_ids=(100,))
    plan = report.plans[0]
    sale_table = next(s for s in sections(report) if s.anchor == plan.anchor).tables[0]
    assert sale_table.caption == "Sales Data"
    assert "**Sales Data**" in render_markdown(report)
    assert "<caption>Sales Data</caption>" in render_html(report)
    assert sale_table.headings[3:5] == ("Sales tax/batch", "Broker fee/batch")
    assert sale_table.rows[0][3:5] == ("288.00", "0.00")
    assert sale_table.rows[1][3:5] == ("360.00", "100.00")
    assert sale_table.rows[2][3:5] == ("324.00", "90.00")
    assert sale_table.rows[3][3:5] == ("Unavailable", "Unavailable")
    for outcome in plan.outcomes:
        if outcome.fees is not None:
            assert outcome.fees == outcome.sales_tax + outcome.broker_fee
        else:
            assert outcome.sales_tax is None
            assert outcome.broker_fee is None
    for render in (render_markdown, render_html):
        text = render(report)
        assert "Sale fees/batch" not in text
        assert "Sales tax/batch" in text
        assert "Broker fee/batch" in text


def test_default_sale_fees() -> None:
    """Charge broker fees for sell and history bases, never sales to buy orders."""
    report = build_report(demo_inputs(), product_ids=(100,))
    assert report.sales_tax_rate == D("0.036")
    assert report.broker_fee_rate == D("0.01")
    plan = report.plans[0]
    for outcome in plan.outcomes:
        rate = D("0.036") if outcome.basis == "buy_5pct" else D("0.046")
        assert outcome.net_per_unit == outcome.price * (1 - rate)
        assert outcome.fees == outcome.price * plan.produced * rate
        assert outcome.profit_per_unit == outcome.net_per_unit - plan.unit_cost
        assert outcome.return_pct == (
            100 * outcome.profit_per_unit * plan.produced / plan.total
        )
    row = next(csv.DictReader(io.StringIO(render_csv(report))))
    assert row["sales_tax_rate"] == "0.036"
    assert row["broker_fee_rate"] == "0.01"
    assert row["jita_history_average_net_proceeds_per_unit"] == "858.600"
    for render in (render_markdown, render_html):
        assert "Sales tax: 3.60%; broker fee: 1.00%" in render(report)


def test_item_index_includes_batch_cost_and_job_hours() -> None:
    """Match strategy summary costs and hours without displaying anchor text."""
    report = build_report(demo_inputs(), product_ids=(100,))
    detail_sections = sections(report)
    index = next(s for s in detail_sections if s.anchor == "item-index").tables[0]
    summary = next(s for s in detail_sections if s.anchor == "item-100").tables[0]
    assert index.headings == (
        "Product",
        "Strategy",
        "Units",
        "m3",
        "Batch cost ISK",
        "Unit cost ISK",
        "Job-hours",
        "Status",
    )
    for row, strategy_row in zip(index.rows, summary.rows, strict=True):
        assert row[3:7] == strategy_row[4:8]
    for render in (render_markdown, render_html):
        assert "Detail anchor" not in render(report)


@pytest.mark.parametrize("volume", (D("0.015"), D(0), None))
def test_strategy_summary_total_volume(volume: Decimal | None) -> None:
    """Multiply volume by produced units, not runs or static portion size."""
    data = demo_inputs()
    data.items[100] = replace(data.items[100], portion_size=100, volume=volume)
    data.blueprints[1100] = replace(data.blueprints[1100], output=100)
    report = build_report(data, product_ids=(100,))
    summary = next(s for s in sections(report) if s.anchor == "item-100").tables[0]
    index = next(s for s in sections(report) if s.anchor == "item-index").tables[0]
    assert index.headings[2:4] == ("Units", "m3")
    assert [row[2:4] for row in index.rows] == [row[3:5] for row in summary.rows]
    assert summary.headings[3:5] == ("Units", "m3")
    for row in summary.rows:
        assert row[3] == "1000"
        assert row[4] == ("Unavailable" if volume is None else f"{volume * 1000:,.2f}")
    for render in (render_markdown, render_html):
        assert "m3" in render(report)


def test_product_strategy_summary_uses_portion_size() -> None:
    """Label the summary and show static portion size, not recipe output."""
    data = demo_inputs()
    data.items[100] = replace(data.items[100], portion_size=100)
    report = build_report(data, product_ids=(100,))
    summary = next(s for s in sections(report) if s.anchor == "item-100")
    assert not summary.paragraphs
    summary_table = summary.tables[0]
    assert summary_table.caption == "Strategy Summaries"
    assert summary_table.headings[2] == "Portion Size"
    assert all(row[2] == "100" for row in summary_table.rows)
    markdown = render_markdown(report)
    html = render_html(report)
    assert "**Strategy Summaries**" in markdown
    assert "<caption>Strategy Summaries</caption>" in html
    for text in (markdown, html):
        assert "Output/run" not in text
        assert "Static portion size:" not in text
        assert "Manufacturing output per run is reported separately below." not in text


def test_item_index_sorted_by_hidden_market_path() -> None:
    """Sort paths before names, retaining strategy order and matching links."""
    data = demo_inputs()
    data.items[100] = replace(data.items[100], market_path="Z/Assemblies")
    data.items[200] = replace(data.items[200], market_path="A/Modules")
    data.items[300] = replace(data.items[300], market_path=None)
    report = build_report(data, product_ids=(100, 200, 300))
    original_order = tuple(report.plans)
    index = next(s for s in sections(report) if s.anchor == "item-index").tables[0]
    expected = [
        p for type_id in (200, 100, 300) for p in report.plans if p.type_id == type_id
    ]
    assert [row[0] for row in index.rows] == [
        data.items[p.type_id].name for p in expected
    ]
    for row, plan in enumerate(expected):
        assert index.cell_links[row, 0] == f"item-{plan.type_id}"
        assert (row, 1) not in index.cell_links
        assert (row, 1) not in index.cell_anchors
    assert report.plans == original_order
    for render in (render_markdown, render_html):
        assert "A/Modules" not in render(report)
    data.items[100] = replace(data.items[100], market_path="A/Modules")
    tied_index = next(s for s in sections(report) if s.anchor == "item-index").tables[0]
    assert tied_index.rows[0][0] == data.items[100].name


def test_readable_reports_use_names_not_game_id_columns() -> None:
    """Keep numeric CSV identities while using names throughout detail tables."""
    data = demo_inputs()
    report = build_report(data, product_ids=(100,))
    for section in sections(report):
        for detail_table in section.tables:
            assert "Type ID" not in detail_table.headings
            assert "Product ID" not in detail_table.headings
            assert "Blueprint ID" not in detail_table.headings
            assert all(
                len(row) == len(detail_table.headings) for row in detail_table.rows
            )
    for render in (render_markdown, render_html):
        text = render(report)
        assert "Synthetic T1 assembly Blueprint" in text
        assert "Synthetic component Blueprint" in text
        assert "make-100-1" in text
    row = next(csv.DictReader(io.StringIO(render_csv(report))))
    assert row["type_id"] == "100"
    assert row["jita_station_id"] == "60003760"
    del data.items[1100]
    assert "UNKNOWN 1100" in render_html(report)


@pytest.mark.parametrize("copy_inputs", ("none", "priced", "missing"))
def test_copying_job_columns_and_total_cost(copy_inputs: str) -> None:
    """Include copying installation and consumables, preserving unknown prices."""
    data = demo_inputs()
    if copy_inputs != "none":
        data.blueprints[1100] = replace(
            data.blueprints[1100],
            copying_materials=(Material(type_id=3, quantity=20),),
        )
    if copy_inputs == "missing":
        del data.input_prices[3]
    report = build_report(data, product_ids=(100,))
    plan = report.plans[0]
    copy = next(j for j in plan.jobs if j.activity == "copying")
    job_table = next(
        s for s in sections(report) if s.anchor == f"{plan.anchor}-copying"
    ).tables[0]
    assert "Remaining runs" not in job_table.headings
    assert job_table.headings[-2:] == ("Copying Cost ISK", "Depends on")
    values = dict(zip(job_table.headings, job_table.rows[0], strict=True))
    expected_cost = (
        "Unavailable"
        if copy_inputs == "missing"
        else f"{copy.total_fee + sum(m.quantity * data.input_prices[m.type_id] for m in copy.inputs):,.2f}"
    )
    assert values["Copying Cost ISK"] == expected_cost
    assert "Duration seconds" not in job_table.headings
    assert values["Job-hours"] == f"{copy.duration / 3600:,.2f}"
    for render in (render_markdown, render_html):
        assert "Copying Cost ISK" in render(report)


@pytest.mark.parametrize("missing_price", (False, True))
def test_invention_job_result_probability_and_cost(missing_price: bool) -> None:
    """Show the actual invented blueprint and costs excluding source copying."""
    data = demo_inputs()
    if missing_price:
        del data.input_prices[3]
    report = build_report(data, product_ids=(200,))
    plan = report.plans[0]
    invention = next(j for j in plan.jobs if j.activity == "invention")
    node = plan.nodes[0]
    job_table = next(
        s for s in sections(report) if s.anchor == f"{plan.anchor}-invention"
    ).tables[0]
    values = dict(zip(job_table.headings, job_table.rows[0], strict=True))
    assert "Remaining runs" not in job_table.headings
    assert job_table.headings[2] == "Attempts"
    assert job_table.headings[-2:] == ("Invention Cost ISK", "Depends on")
    assert values["Depends on"] == ", ".join(invention.dependencies)
    assert values["Success Probability"] == f"{node.probability * 100:,.2f}%"
    assert values["Result"] == "Synthetic T2 module Blueprint"
    me_te_index = job_table.headings.index("ME / TE")
    assert job_table.headings[me_te_index - 2 : me_te_index] == (
        "Result",
        "Licensed runs/BPC",
    )
    assert values["Licensed runs/BPC"] == str(invention.licensed_runs)
    assert values["ME / TE"] == "2 / 4"
    expected_cost = (
        "Unavailable"
        if missing_price
        else f"{invention.total_fee + sum(m.quantity * data.input_prices[m.type_id] for m in invention.inputs):,.2f}"
    )
    assert values["Invention Cost ISK"] == expected_cost
    assert "Duration seconds" not in job_table.headings
    assert values["Job-hours"] == f"{invention.duration / 3600:,.2f}"
    for render in (render_markdown, render_html):
        assert "Success Probability" in render(report)
        assert "Invention Cost ISK" in render(report)


@pytest.mark.parametrize("missing_price", (False, True))
def test_manufacturing_cost_excludes_own_bpc_preparation(missing_price: bool) -> None:
    """Value each job's inputs consistently with its material input table."""
    data = demo_inputs()
    data.blueprints[1100] = replace(data.blueprints[1100], max_runs=3)
    if missing_price:
        del data.input_prices[1]
    report = build_report(data, product_ids=(100,))
    for plan in report.plans:
        detail = sections(report)
        manufacturing = next(
            s for s in detail if s.anchor == f"{plan.anchor}-manufacturing"
        ).tables[0]
        assert manufacturing.headings[-2:] == ("Manufacturing Cost ISK", "Depends on")
        for job, row in zip(
            (j for j in plan.jobs if j.activity == "manufacturing"),
            manufacturing.rows,
            strict=True,
        ):
            values = dict(zip(manufacturing.headings, row, strict=True))
            assert values["Job-hours"] == f"{job.duration / 3600:,.2f}"
            assert "Duration seconds" not in manufacturing.headings
            if missing_price:
                assert row[-2] == "Unavailable"
                continue
            material_cost = D(0)
            for material in job.inputs:
                child = next(
                    (n for n in plan.nodes if n.type_id == material.type_id), None
                )
                price = (
                    child.cost / child.required
                    if child
                    else data.input_prices[material.type_id]
                )
                material_cost += material.quantity * price
            assert row[-2] == f"{job.total_fee + material_cost:,.2f}"
        if not missing_price:
            for node in plan.nodes:
                jobs = [j for j in plan.jobs if j.job_id in node.job_ids]
                assert node.cost > sum(j.total_fee for j in jobs)


@pytest.mark.parametrize("product_id", (100, 200))
def test_jobs_grouped_by_activity_with_summary(product_id: int) -> None:
    """Keep each job in its activity group and reconcile cost/time totals."""
    report = build_report(demo_inputs(), product_ids=(product_id,))
    plan = report.plans[0]
    detail = sections(report)
    start = next(i for i, s in enumerate(detail) if s.anchor == plan.anchor)
    end = next(i for i, s in enumerate(detail) if s.anchor == f"{plan.anchor}-inputs")
    area = detail[start + 1 : end]
    assert [s.anchor for s in area] == [
        f"{plan.anchor}-{suffix}"
        for suffix in (
            "copying",
            "invention",
            "manufacturing",
            "installation-costs",
        )
    ]
    for render in (render_markdown, render_html):
        text = render(report)
        assert "Blueprints, invention and output allocation" not in text
        assert "BPC material inputs to manufacturing" not in text
    assert [s.title for s in area if s.level == 4] == [
        "Copying",
        "Invention",
        "Manufacturing",
        "Installation Costs",
    ]
    for activity in ("copying", "invention", "manufacturing"):
        group = next(s for s in area if s.anchor == f"{plan.anchor}-{activity}")
        jobs = [j for j in plan.jobs if j.activity == activity]
        assert [row[0] for row in group.tables[0].rows] == [j.job_id for j in jobs]
        assert len(group.tables) == 1
        if not jobs:
            assert group.paragraphs == ("No jobs required for this activity.",)
    summary = area[-1]
    assert summary.title == "Installation Costs"
    (charges,) = summary.tables
    assert charges.headings == (
        "Activity",
        "Job",
        "EIV ISK",
        "PTV ISK",
        "Index charge",
        "Facility charge",
        "SCC charge",
        "Alpha charge",
        "Total installation ISK",
        "Job-hours",
    )
    expected_jobs = [
        j
        for activity in ("copying", "invention", "manufacturing")
        for j in plan.jobs
        if j.activity == activity
    ]
    assert [row[:2] for row in charges.rows] == [
        (j.activity.capitalize(), j.job_id) for j in expected_jobs
    ]
    assert [row[-1] for row in charges.rows] == [
        f"{j.duration / 3600:,.2f}" for j in expected_jobs
    ]
    for render in (render_markdown, render_html):
        text = render(report)
        assert "Job Summary" not in text
        assert "Installation cost and time totals" not in text
        assert text.index("Installation Costs") < text.index("Per-job material inputs")


def test_job_output_omits_unique_source_bpo_id() -> None:
    """Keep blueprint types visible but omit the owned BPO instance column."""
    report = build_report(demo_inputs(), product_ids=(100,))
    jobs = next(
        s for s in sections(report) if s.anchor == f"{report.plans[0].anchor}-copying"
    )
    job_table = jobs.tables[0]
    assert "Source BPO item" not in job_table.headings
    assert "Blueprint" in job_table.headings
    assert all(len(row) == len(job_table.headings) for row in job_table.rows)
    assert "Source BPO item" not in render_markdown(report)
    assert "Source BPO item" not in render_html(report)


def test_item_index_has_only_product_two_way_links() -> None:
    """Keep product navigation while rendering strategy labels as plain text."""
    report = build_report(demo_inputs(), product_ids=(100,))
    markdown = render_markdown(report)
    html = render_html(report)
    name = report.data.items[100].name
    assert f"[{name}](#item-100)" in markdown
    assert f'<a href="#item-100">{name}</a>' in html
    assert markdown.count('<a id="index-item-100"></a>') == 1
    assert html.count('id="index-item-100"') == 1
    assert "[Back to item index](#index-item-100)" in markdown
    assert '<a href="#index-item-100">Back to item index</a>' in html
    for plan in report.plans:
        assert f"index-{plan.anchor}" not in markdown
        assert f"index-{plan.anchor}" not in html
        assert f"<td>{plan.strategy}</td>" in html
        assert f'<a id="{plan.anchor}"></a>' in markdown
        assert f'id="{plan.anchor}"' in html


def test_strategy_summaries_have_two_way_links() -> None:
    """Link summary strategies to details and return to the matching row."""
    report = build_report(demo_inputs(), product_ids=(100, 200))
    detail_sections = sections(report)
    markdown = render_markdown(report)
    html = render_html(report)
    for plan in report.plans:
        summary = next(
            s for s in detail_sections if s.anchor == f"item-{plan.type_id}"
        ).tables[0]
        row = next(
            i for i, cells in enumerate(summary.rows) if cells[0] == plan.strategy
        )
        anchor = f"summary-{plan.anchor}"
        assert summary.cell_links[row, 0] == plan.anchor
        assert summary.cell_anchors[row, 0] == anchor
        assert f"[{plan.strategy}](#{plan.anchor})" in markdown
        assert f'<a href="#{plan.anchor}">{plan.strategy}</a>' in html
        assert f'<a id="{anchor}"></a>' in markdown
        assert f'id="{anchor}"' in html
        assert f"[Back to Strategy Summaries](#{anchor})" in markdown
        assert f'<a href="#{anchor}">Back to Strategy Summaries</a>' in html


def test_external_shopping_list_is_raw_text() -> None:
    """Show combined purchases as raw text without a duplicate detail table."""
    data = demo_inputs()
    report = build_report(data, product_ids=(100,))
    plan = report.plans[0]
    plan.shopping = [
        Purchase(type_id=1, quantity=1200, unit_price=D(3), reason="recipe"),
        Purchase(type_id=1, quantity=34, unit_price=D(3), reason="invention"),
        Purchase(type_id=2, quantity=7, unit_price=None, reason="recipe"),
    ]
    shopping = next(
        s for s in sections(report) if s.anchor == f"{plan.anchor}-shopping"
    )
    assert shopping.title == "External Shopping List"
    assert not shopping.tables
    expected = (
        "Name                        Quantity\n"
        "Synthetic mineral               1234\n"
        "Synthetic reaction product         7"
    )
    assert shopping.raw_text == expected
    markdown = render_markdown(report)
    html = render_html(report)
    assert f"```text\n{expected}\n```" in markdown
    assert f"<pre>{expected}</pre>" in html
    assert "| Name" not in markdown
    assert '<th scope="col">Name</th>' not in html
    assert "Jita sell 5% ISK/unit" not in markdown
    assert "Jita sell 5% ISK/unit" not in html
    assert '<th scope="col">Valuation</th>' in html


def test_rounded_attempts() -> None:
    """Round per successful BPC, not after combining successes."""
    assert rounded_attempts(D("0.4")) == 3
    assert rounded_attempts(D(1)) == 1
    for probability in (D(0), D(-1), D("1.1"), D("NaN")):
        with pytest.raises(ValueError):
            rounded_attempts(probability)


@pytest.mark.parametrize("reaction_only", (False, True))
def test_omit_make_without_subassemblies(reaction_only: bool) -> None:
    """Omit redundant make rows and detail sections across all output formats."""
    data = demo_inputs()
    data.blueprints[1100] = replace(
        data.blueprints[1100],
        materials=(Material(type_id=2 if reaction_only else 1, quantity=3),),
    )
    if reaction_only:
        data.blueprints[1002] = replace(
            data.blueprints[1010], blueprint_id=1002, product_id=2
        )
    report = build_report(data, product_ids=(100,))
    assert [plan.strategy for plan in report.plans] == ["buy-all-inputs"]
    rows = list(csv.DictReader(io.StringIO(render_csv(report))))
    assert len(rows) == 1
    for text in (render_csv(report), render_markdown(report), render_html(report)):
        assert "production-100-make-all-inputs" not in text
    assert report.plans[0].status == "complete"


def test_buy_and_make_reconcile() -> None:
    """Include copying once and purchase reaction inputs in either strategy."""
    report = build_report(demo_inputs(), product_ids=(100,))
    buy, make = report.plans
    assert buy.produced == make.produced == 10
    assert buy.status == make.status == "complete"
    assert len(buy.nodes) == 1
    assert len(make.nodes) == 2
    assert {line.type_id for line in make.shopping} == {1, 2}
    assert buy.total == D("863.592")
    assert make.total == D("413.2737")
    for plan in report.plans:
        external = known_sum(line.cost for line in plan.shopping)
        fees = known_sum(job.total_fee for job in plan.jobs)
        assert external is not None and fees is not None and plan.total is not None
        assert plan.total == external + fees
        assert plan.unit_cost == plan.total / plan.produced
        assert all(job.activity != "reaction" for job in plan.jobs)
        assert any(job.activity == "copying" for job in plan.jobs)
        assert plan.nodes[0].cost == plan.total


def test_best_original_preserves_pair() -> None:
    """Rank actual originals by ME, TE, then lower item ID."""
    data = demo_inputs()
    data.originals = (
        Original(blueprint_id=1100, item_id=8, me=9, te=20),
        Original(blueprint_id=1100, item_id=9, me=10, te=4),
        Original(blueprint_id=1100, item_id=7, me=10, te=4),
        *data.originals[1:],
    )
    plan = build_report(data, product_ids=(100,)).plans[0]
    copy = next(job for job in plan.jobs if job.activity == "copying")
    assert (copy.original_item_id, copy.me, copy.te) == (7, 10, 4)


@pytest.mark.parametrize("product_id", (100, 200))
def test_copy_consumables_per_licensed_run(product_id: int) -> None:
    """Cost copying inputs once, including split copies and invention attempts."""
    data = demo_inputs()
    data.blueprints[1100] = replace(data.blueprints[1100], max_runs=2)
    baseline = build_report(data, product_ids=(product_id,)).plans[0]
    data.blueprints[1100] = replace(
        data.blueprints[1100],
        max_runs=2,
        copying_materials=(Material(type_id=3, quantity=20),),
    )
    plan = build_report(data, product_ids=(product_id,)).plans[0]
    copies = [j for j in plan.jobs if j.activity == "copying"]
    assert len(copies) > 1
    assert all(j.inputs == (Material(type_id=3, quantity=20 * j.runs),) for j in copies)
    added_quantity = 20 * sum(j.licensed_runs for j in copies)
    added_cost = added_quantity * data.input_prices[3]
    assert plan.total == baseline.total + added_cost
    assert plan.nodes[0].cost == plan.total
    assert (
        plan.nodes[0].preparation_cost
        == baseline.nodes[0].preparation_cost + added_cost
    )
    assert sum(p.quantity for p in plan.shopping if p.type_id == 3) == (
        sum(p.quantity for p in baseline.shopping if p.type_id == 3) + added_quantity
    )
    del data.input_prices[3]
    incomplete = build_report(data, product_ids=(product_id,)).plans[0]
    assert incomplete.total is None
    assert incomplete.nodes[0].preparation_cost is None
    assert any(p.type_id == 3 for p in incomplete.shopping)


def test_copy_limits_split_material_rounding() -> None:
    """Round quantities per BPC-sized job instead of rounding the total."""
    data = demo_inputs()
    data.blueprints[1100] = replace(
        data.blueprints[1100],
        max_runs=3,
        materials=(Material(type_id=1, quantity=2),),
    )
    plan = build_report(data, product_ids=(100,)).plans[0]
    assert [job.runs for job in plan.jobs if job.activity == "manufacturing"] == [
        3,
        3,
        3,
        1,
    ]
    assert sum(line.quantity for line in plan.shopping) == 20
    assert sum(job.runs for job in plan.jobs if job.activity == "copying") == 10


@pytest.mark.parametrize(
    ("product_id", "licensed_runs", "expected_reference", "manufacturing_runs"),
    (
        (200, 20, 10, (10,)),
        (200, 4, 10, (4, 4, 2)),
        (300, 3, 3, (3,)),
    ),
)
def test_invention_product_quantity_sets_licensed_runs(
    product_id: int,
    licensed_runs: int,
    expected_reference: int,
    manufacturing_runs: tuple[int, ...],
) -> None:
    """Use static invention quantities rather than family-based run constants."""
    data = demo_inputs()
    blueprint_id = 1200 if product_id == 200 else 1300
    data.inventions = tuple(
        replace(route, licensed_runs=licensed_runs)
        if route.target_blueprint_id == blueprint_id
        else route
        for route in data.inventions
    )
    plan = build_report(data, product_ids=(product_id,)).plans[0]
    assert plan.status == "complete"
    assert plan.reference_runs == expected_reference
    jobs = [j for j in plan.jobs if j.activity == "manufacturing"]
    assert tuple(j.runs for j in jobs) == manufacturing_runs
    assert all(j.licensed_runs == licensed_runs for j in jobs)
    assert [j.remaining_runs for j in jobs] == [
        licensed_runs - runs for runs in manufacturing_runs
    ]
    assert all(
        j.licensed_runs == licensed_runs for j in plan.jobs if j.activity == "invention"
    )
    assert plan.produced == expected_reference * data.blueprints[blueprint_id].output
    assert plan.unit_cost == plan.total / plan.produced


@pytest.mark.parametrize("licensed_runs", (0, -1))
def test_invalid_invention_product_quantity_is_incomplete(licensed_runs: int) -> None:
    """Invalid quantities are surfaced rather than becoming free or crashing."""
    data = demo_inputs()
    data.inventions = tuple(
        replace(route, licensed_runs=licensed_runs) for route in data.inventions
    )
    for product_id in (200, 300):
        plan = build_report(data, product_ids=(product_id,)).plans[0]
        assert plan.status == "incomplete"
        assert any("Invalid invented BPC runs" in warning for warning in plan.warnings)


def test_invention_budget_and_ship_runs() -> None:
    """Budget three attempts per BPC and do not copy a T2 original."""
    report = build_report(demo_inputs(), product_ids=(200, 300))
    for plan in report.plans:
        inventions = [job for job in plan.jobs if job.activity == "invention"]
        assert sum(job.runs for job in inventions) == 3
        node = plan.nodes[0]
        assert (node.me, node.te) == (2, 4)
        assert node.attempts_per_bpc == 3
        assert node.probability is not None
        assert all(
            job.blueprint_id != node.blueprint_id
            for job in plan.jobs
            if job.activity == "copying"
        )
        assert plan.reference_runs == (1 if plan.type_id == 300 else 10)
        assert plan.produced == plan.reference_runs


@pytest.mark.parametrize("branch_quantity", (1, 2, 3, 7))
def test_shared_component_demand_and_surplus(branch_quantity: int) -> None:
    """Aggregate a diamond dependency before sizing and charging its jobs."""
    data = demo_inputs()
    data.items[101] = Item(type_id=101, name="Second branch")
    data.adjusted_prices[101] = D(40)
    data.blueprints[1101] = Blueprint(
        blueprint_id=1101,
        product_id=101,
        output=1,
        max_runs=100,
        materials=(Material(type_id=10, quantity=branch_quantity),),
        manufacturing_seconds=100,
        copying_seconds=10,
    )
    data.originals += (Original(blueprint_id=1101, item_id=1010, me=0, te=0),)
    data.blueprints[1100] = replace(
        data.blueprints[1100],
        materials=(Material(type_id=101, quantity=1), Material(type_id=10, quantity=1)),
    )
    data.blueprints[1010] = replace(data.blueprints[1010], output=3)
    plan = build_report(data, product_ids=(100,)).plans[1]
    shared = next(node for node in plan.nodes if node.type_id == 10)
    expected = (branch_quantity + 1) * 10
    assert shared.required == expected
    assert shared.produced == ((expected + 2) // 3) * 3
    assert sum(node.type_id == 10 for node in plan.nodes) == 1
    external = known_sum(line.cost for line in plan.shopping)
    fees = known_sum(job.total_fee for job in plan.jobs)
    assert external is not None and fees is not None
    assert plan.total == external + fees
    assert plan.nodes[0].cost == plan.total


def test_missing_required_inputs_are_unknown() -> None:
    """Missing BPOs or prices never become free or silently purchased."""
    data = demo_inputs()
    data.originals = tuple(o for o in data.originals if o.blueprint_id != 1010)
    report = build_report(data, product_ids=(100,))
    assert report.plans[0].status == "complete"
    assert report.plans[1].total is None
    assert "BPO" in " ".join(report.plans[1].warnings)
    data = demo_inputs()
    data.adjusted_prices.pop(1)
    assert build_report(data, product_ids=(100,)).plans[0].total is None
    data = demo_inputs()
    data.input_prices.pop(10)
    plan = build_report(data, product_ids=(100,)).plans[0]
    assert plan.total is None
    assert all(outcome.profit_per_unit is None for outcome in plan.outcomes)


def test_cycle_and_ambiguous_routes() -> None:
    """Retain incomplete estimates rather than recurse forever or choose routes."""
    data = demo_inputs()
    data.blueprints[1010] = replace(
        data.blueprints[1010], materials=(Material(type_id=100, quantity=1),)
    )
    assert "cycle" in " ".join(build_report(data, product_ids=(100,)).plans[1].warnings)
    data = demo_inputs()
    data.blueprints[9999] = replace(data.blueprints[1100], blueprint_id=9999)
    assert "ambiguous" in " ".join(
        build_report(data, product_ids=(100,)).plans[0].warnings
    )


def test_cross_format_values_and_escaping() -> None:
    """Exports share one model, preserve unknowns and escape untrusted names."""
    data = demo_inputs()
    data.items[100] = replace(data.items[100], name='<script>alert("x")</script>|A')
    report = build_report(data, product_ids=(100,))
    text = render_csv(report)
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == 2
    assert rows[0]["name"] == data.items[100].name
    assert rows[0]["jita_avg_daily_sales"] == "15"
    assert rows[0]["jita_history_days_present"] == "10"
    assert D(rows[0]["jita_sell_5pct_total_profit"]) == (
        D(rows[0]["jita_sell_5pct_net_proceeds_per_unit"]) * 10
        - D(rows[0]["allocated_cost"])
    )
    html = render_html(report)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert '<th scope="col">' in html
    assert "https://" not in html
    markdown = render_markdown(report)
    assert "\\|" in markdown
    assert render_markdown(report) == markdown
    assert format_markdown(markdown) == markdown
    assert "production-100-buy-all-inputs" in markdown
    assert "production-100-buy-all-inputs" in html


def test_write_protection(tmp_path: Path) -> None:
    """Preflight collisions before writing and permit explicit overwrite."""
    report = build_report(demo_inputs(), product_ids=(100,))
    paths = write_reports(report, destination=tmp_path)
    assert {path.suffix for path in paths} == {".csv", ".md", ".html"}
    with pytest.raises(FileExistsError):
        write_reports(report, destination=tmp_path)
    write_reports(report, destination=tmp_path, overwrite=True)


def test_group_pages_and_cross_file_navigation(tmp_path: Path) -> None:
    """Partition by static group and resolve every exported link and anchor."""
    data = demo_inputs()
    for type_id, group_id, group_name in (
        (100, 25, "Frigate <&> / group"),
        (200, 53, "Energy Weapon"),
        (300, 53, "Energy Weapon"),
    ):
        data.items[type_id] = replace(
            data.items[type_id],
            group_id=group_id,
            group_name=group_name,
            category_id=6 if type_id == 100 else 7,
            category_name="Ship <&>" if type_id == 100 else "Module",
        )
    report = build_report(data, product_ids=(100, 200, 300))
    paths = write_reports(report, destination=tmp_path)
    assert tmp_path / "industry-report.csv" in paths
    assert not (tmp_path / "industry-report.html").exists()
    assert not (tmp_path / "industry-report.md").exists()
    expected = {
        "index",
        "profit-opportunities",
        "assumptions",
        "sources",
        "group-25",
        "group-53",
    }

    class Links(HTMLParser):
        """Collect output navigation for local link verification."""

        def __init__(self) -> None:
            super().__init__()
            self.ids: set[str] = set()
            self.hrefs: list[str] = []

        def handle_starttag(
            self, tag: str, attrs: list[tuple[str, str | None]]
        ) -> None:
            for key, value in attrs:
                if key == "id" and value is not None:
                    assert value not in self.ids
                    self.ids.add(value)
                if key == "href" and value is not None:
                    self.hrefs.append(value)

    for folder, suffix in (("html", ".html"), ("markdown", ".md")):
        pages = {p.stem: p.read_text() for p in (tmp_path / folder).glob(f"*{suffix}")}
        assert set(pages) == expected
        assert f"group-25{suffix}#item-100" in pages["index"]
        assert f"index{suffix}#index-item-100" in pages["group-25"]
        assert f"group-53{suffix}#production-200-" in pages["profit-opportunities"]
        assert 'id="item-200"' not in pages["group-25"]
        assert 'id="item-100"' not in pages["group-53"]
        assert "Strategy Summaries" not in pages["index"]
        anchors: dict[str, set[str]] = {}
        hrefs: dict[str, list[str]] = {}
        for stem, text in pages.items():
            if folder == "html":
                top_nav = text.split('<nav aria-label="Report contents">')[1].split(
                    "</nav>"
                )[0]
                assert f'href="{stem}.html"' not in top_nav
                assert 'href="#' not in top_nav
                parser = Links()
                parser.feed(text)
                anchors[stem] = parser.ids
                hrefs[stem] = parser.hrefs
            else:
                anchors[stem] = set(re.findall(r'<a id="([^"]+)"', text))
                hrefs[stem] = re.findall(r"\]\(([^)]+)\)", text)
                assert format_markdown(text) == text
        for stem, links in hrefs.items():
            for link in links:
                filename, _, anchor = link.partition("#")
                target = Path(filename).stem if filename else stem
                assert target in pages, link
                if anchor:
                    assert anchor in anchors[target], link
    assert (
        "Frigate &lt;&amp;&gt; / group" in (tmp_path / "html/group-25.html").read_text()
    )
    index = (tmp_path / "html/index.html").read_text()
    sidebar = re.search(
        r'<nav class="group-sidebar" aria-label="Product groups">(.*?)</nav>',
        index,
        re.DOTALL,
    )
    assert sidebar is not None
    assert 'href="#index-group-25"' in sidebar[1]
    assert 'href="#index-group-53"' in sidebar[1]
    for folder, suffix in (("html", "html"), ("markdown", "md")):
        text = (tmp_path / folder / f"index.{suffix}").read_text()
        assert 'id="index-group-25"' in text
        assert 'id="index-group-53"' in text
        assert (
            text.count("<table>") == 2
            if folder == "html"
            else text.count("| Product") == 2
        )
    assert "profit-opportunities.html" not in sidebar[1]
    assert sidebar[1].index("Module") < sidebar[1].index("Ship &lt;&amp;&gt;")
    assert re.search(
        r"Module</h3>\s*<ul>.*?href=\"#index-group-53\".*?</ul>",
        sidebar[1],
        re.DOTALL,
    )
    assert re.search(
        r"Ship &lt;&amp;&gt;</h3>\s*<ul>.*?href=\"#index-group-25\".*?</ul>",
        sidebar[1],
        re.DOTALL,
    )
    top_navigation = index.split('<nav aria-label="Report contents">')[1].split(
        "</nav>"
    )[0]
    assert "profit-opportunities.html" in top_navigation
    assert "group-25.html" not in top_navigation
    assert (
        'aria-label="Product groups"'
        not in (tmp_path / "html/group-25.html").read_text()
    )
    detail = (tmp_path / "html/group-53.html").read_text()
    detail_nav = detail.split('<nav aria-label="Report contents">')[1].split("</nav>")[
        0
    ]
    assert 'href="group-' not in detail_nav
    assert 'href="index.html"' in detail_nav
    product_sidebar = re.search(
        r'<nav class="group-sidebar" aria-label="Products on this page">(.*?)</nav>',
        detail,
        re.DOTALL,
    )
    assert product_sidebar is not None
    assert 'href="#item-200"' in product_sidebar[1]
    assert 'href="#item-300"' in product_sidebar[1]
    assert 'href="#item-100"' not in product_sidebar[1]
    assert 'href="#item-200"' not in detail_nav
    opportunities = (tmp_path / "html/profit-opportunities.html").read_text()
    opportunity_nav = opportunities.split('<nav aria-label="Report contents">')[
        1
    ].split("</nav>")[0]
    assert 'href="index.html"' in opportunity_nav
    assert 'href="assumptions.html"' in opportunity_nav
    assert 'href="sources.html"' in opportunity_nav
    assert 'href="group-' not in opportunity_nav
    assert 'href="group-53.html#production-200-' in opportunities
    for stem in ("assumptions", "sources"):
        page = (tmp_path / f"html/{stem}.html").read_text()
        top_nav = page.split('<nav aria-label="Report contents">')[1].split("</nav>")[0]
        assert 'href="group-' not in top_nav
        assert 'href="index.html"' in top_nav
        assert 'href="profit-opportunities.html"' in top_nav


def test_nested_output_collision_preflight(tmp_path: Path) -> None:
    """A nested collision or non-directory stops before any report file writes."""
    report = build_report(demo_inputs(), product_ids=(100,))
    (tmp_path / "html").mkdir()
    blocker = tmp_path / "html/index.html"
    blocker.write_text("preserve")
    with pytest.raises(FileExistsError):
        write_reports(report, destination=tmp_path)
    assert blocker.read_text() == "preserve"
    assert not (tmp_path / "industry-report.csv").exists()
    assert not (tmp_path / "markdown").exists()
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / "markdown").write_text("not a directory")
    with pytest.raises(ValueError, match="not a directory"):
        write_reports(report, destination=blocked, overwrite=True)
    assert not (blocked / "industry-report.csv").exists()


@pytest.mark.parametrize("empty", (False, True))
def test_opportunities_by_hub(tmp_path: Path, empty: bool) -> None:
    """Keep every opportunity once, remove Hub, and link each hub table locally."""
    report = build_report(demo_inputs(), product_ids=(100,))
    if empty:
        for plan in report.plans:
            plan.outcomes = [replace(o, return_pct=None) for o in plan.outcomes]
    original = profit_opportunities(report).tables[0]
    page = report_pages(report)["profit-opportunities"]
    hub_sections = page[1:]
    assert [s.title for s in hub_sections] == [
        "Jita",
        "Amarr",
        "Dodixie",
        "Hek",
        "Rens",
    ]
    expected_headings = original.headings[:2] + original.headings[3:]
    for section in hub_sections:
        entry = section.tables[0]
        assert entry.headings == expected_headings
        indices = [i for i, row in enumerate(original.rows) if row[2] == section.title]
        assert entry.rows == tuple(
            original.rows[i][:2] + original.rows[i][3:] for i in indices
        )
        for row, source_row in enumerate(indices):
            for col in (0, 1):
                assert (
                    entry.cell_links[row, col] == original.cell_links[source_row, col]
                )
        if not indices:
            assert section.paragraphs
    write_reports(report, destination=tmp_path)
    html = (tmp_path / "html/profit-opportunities.html").read_text()
    sidebar = re.search(
        r'<nav class="group-sidebar" aria-label="Market hubs">(.*?)</nav>',
        html,
        re.DOTALL,
    )
    assert sidebar is not None
    assert html.count("<table>") == 5
    assert ">Hub</th>" not in html
    for section in hub_sections:
        assert f'href="#{section.anchor}"' in sidebar[1]
        assert f'id="{section.anchor}"' in html


def test_page_rendering_rejects_broken_links_and_duplicate_anchors() -> None:
    """Broken navigation fails rendering rather than silently exporting bad links."""
    with pytest.raises(ValueError, match="Unknown report link"):
        render_pages(
            {"index": [Section(title="Index", anchor="index", index_anchor="missing")]},
            extension="html",
        )
    with pytest.raises(ValueError, match="Duplicate report anchor"):
        render_pages(
            {
                "index": [Section(title="Index", anchor="same")],
                "other": [Section(title="Other", anchor="same")],
            },
            extension="md",
        )


def test_known_invention_cost_and_multiple_bpcs() -> None:
    """Cost all three attempts per BPC, even when source copies must split."""
    data = demo_inputs()
    data.blueprints[1100] = replace(data.blueprints[1100], max_runs=2)
    # Five units per run must not change the ten manufacturing-run reference.
    data.blueprints[1200] = replace(data.blueprints[1200], output=5)
    plan = build_report(data, product_ids=(200,)).plans[0]
    assert plan.produced == 50
    assert plan.total == D("1985.8251")
    assert [j.runs for j in plan.jobs if j.activity == "invention"] == [2, 1]
    data.items[400] = Item(type_id=400, name="Synthetic T1 parent")
    data.blueprints[1400] = Blueprint(
        blueprint_id=1400,
        product_id=400,
        output=1,
        max_runs=100,
        materials=(Material(type_id=200, quantity=6),),
        manufacturing_seconds=100,
        copying_seconds=10,
    )
    data.adjusted_prices[200] = D(100)
    data.originals += (Original(blueprint_id=1400, item_id=4000, me=0, te=0),)
    plan = build_report(data, product_ids=(400,)).plans[1]
    module = next(n for n in plan.nodes if n.type_id == 200)
    assert module.required == 60
    assert module.bpcs == 2
    assert sum(j.runs for j in plan.jobs if j.activity == "invention") == 6
    assert all(j.remaining_runs >= 0 for j in plan.jobs)


def test_fees_depth_zero_cost_and_unavailable_hubs() -> None:
    """Distinguish return from margin and retain missing-market cells."""
    data = demo_inputs()
    key = 60003760, 100
    data.markets[key] = replace(data.markets[key], buy_depth=1)
    data.markets.pop((60008494, 100))
    report = build_report(
        data, product_ids=(100,), sales_tax_rate=D("0.1"), broker_fee_rate=D("0.02")
    )
    plan = report.plans[0]
    assert plan.total is not None
    buy, sell, history = plan.outcomes[:3]
    assert buy.net_per_unit == D(720)
    assert sell.net_per_unit == D(880)
    assert history.net_per_unit == D(792)
    assert history.fees == D(1080)
    assert "insufficient" in buy.status
    assert sell.total_profit == D(8800) - plan.total
    assert sell.return_pct == 100 * (D(8800) - plan.total) / plan.total
    rows = list(csv.DictReader(io.StringIO(render_csv(report))))
    assert rows[0]["amarr_sell_5pct_sale_price"] == ""
    data.input_prices = dict.fromkeys(data.input_prices, D(0))
    data.adjusted_prices = dict.fromkeys(data.adjusted_prices, D(0))
    plan = build_report(data, product_ids=(100,)).plans[0]
    assert plan.total == 0
    assert all(o.return_pct is None for o in plan.outcomes)


def test_source_freshness_and_invalid_values() -> None:
    """Prefer Argus expiry and reject malformed economic inputs."""
    now = datetime(2026, 11, 4, tzinfo=UTC)
    source = Source(
        label="fixture",
        reference="1",
        received_at="2026-01-01T00:00:00Z",
        expires_at="2027-01-01T00:00:00Z",
        argus_expires_at="2026-01-02T00:00:00Z",
    )
    assert source.freshness(now=now) == "stale"
    assert replace(source, argus_expires_at=None).freshness(now=now) == "fresh"
    assert (
        replace(source, argus_expires_at=None, expires_at=None).freshness(now=now)
        == "unknown"
    )
    data = demo_inputs()
    with pytest.raises(ValueError, match="Sale fee"):
        build_report(data, product_ids=(100,), sales_tax_rate=D("NaN"))
    data.input_prices[1] = D(-1)
    with pytest.raises(ValueError, match="nonnegative"):
        build_report(data, product_ids=(100,))


def test_cli_help_demo_and_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Help needs no databases, demo writes all formats, and errors are visible."""
    with pytest.raises(SystemExit) as result:
        main(["--help"])
    assert result.value.code == 0
    destination = tmp_path / "report"
    assert main(["--demo", "--to", str(destination)]) == 0
    assert {p.name for p in destination.iterdir()} == {
        "industry-report.csv",
        "markdown",
        "html",
    }
    assert "0 incomplete" in capsys.readouterr().err
    assert main(["--demo", "--to", str(destination)]) == 1
    with pytest.raises(SystemExit) as result:
        main(["--demo", "--type-id", "-1", "--to", str(tmp_path / "invalid")])
    assert result.value.code == 2
    assert not (tmp_path / "invalid").exists()


@pytest.mark.parametrize(
    "flags",
    (
        ("--owned", "--not-owned"),
        ("--sample", "--owned"),
        ("--sample", "--type-id", "100"),
        ("--not-owned", "--type-id", "100"),
        ("--me", "-1"),
        ("--me", "11"),
        ("--te", "21"),
        ("--type-id", "0"),
        ("--corporation-id", "0"),
        ("--history-stale", "-1"),
    ),
)
def test_cli_selection_validation(tmp_path: Path, flags: tuple[str, ...]) -> None:
    """Reject mixed selections and out-of-range values before writing files."""
    destination = tmp_path / "invalid"
    with pytest.raises(SystemExit) as result:
        main(["--demo", "--to", str(destination), *flags])
    assert result.value.code == 2
    assert not destination.exists()


@pytest.mark.parametrize("selection", ("--owned", "--sample"))
def test_cli_demo_selection(tmp_path: Path, selection: str) -> None:
    """Explicit selection flags reach the collector and write all exports."""
    destination = tmp_path / "report"
    assert main(["--demo", selection, "--to", str(destination)]) == 0
    with (destination / "industry-report.csv").open(newline="") as stream:
        ids = {int(row["type_id"]) for row in csv.DictReader(stream)}
    assert {100, 200, 300} <= ids
    if selection == "--owned":
        assert 10 in ids
