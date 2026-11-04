"""Synthetic acceptance tests kept alongside the isolated industry proof."""

import csv
import io
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from industry_proof import (
    Blueprint,
    Item,
    Material,
    Original,
    Purchase,
    Source,
    build_report,
    known_sum,
    rounded_attempts,
)
from proof_inputs import demo_inputs
from proof_render import (
    render_csv,
    render_html,
    render_markdown,
    sections,
    write_reports,
)
from run_report import main

from pfmsoft.eve_argus.helpers.markdown import format_markdown

D = Decimal


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
        "Batch cost ISK",
        "Unit cost ISK",
        "Job-hours",
        "Status",
    )
    for row, strategy_row in zip(index.rows, summary.rows, strict=True):
        assert row[3:6] == strategy_row[4:7]
    for render in (render_markdown, render_html):
        assert "Detail anchor" not in render(report)


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


def test_job_output_omits_unique_source_bpo_id() -> None:
    """Keep blueprint types visible but omit the owned BPO instance column."""
    report = build_report(demo_inputs(), product_ids=(100,))
    jobs = next(
        s for s in sections(report) if s.anchor == f"{report.plans[0].anchor}-jobs"
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
    bpc_table = next(
        s
        for s in sections(build_report(data, product_ids=(product_id,)))
        if s.anchor == f"{plan.anchor}-bpc-inputs"
    ).tables[0]
    allocated = sum(D(row[-1].replace(",", "")) for row in bpc_table.rows)
    assert abs(allocated - plan.nodes[0].preparation_cost) < D("0.05")
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
    assert len(list(destination.iterdir())) == 3
    assert "0 incomplete" in capsys.readouterr().err
    assert main(["--demo", "--to", str(destination)]) == 1
    assert main(["--demo", "--type-id", "-1", "--to", str(tmp_path / "invalid")]) == 1
    assert not (tmp_path / "invalid").exists()
