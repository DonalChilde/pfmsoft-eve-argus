"""Verify the industry report command's production integration."""

import csv
import io
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from pfmsoft.eve_argus.cli import app
from pfmsoft.eve_argus.cli.reports import industry as command
from pfmsoft.eve_argus.cli.reports._industry_inputs import select_bpo_products
from pfmsoft.eve_argus.reports import industry_render
from pfmsoft.eve_argus.reports.industry import (
    Blueprint,
    Inputs,
    Invention,
    Item,
    Market,
    Material,
    Original,
    build_report,
    rounded_attempts,
)
from pfmsoft.eve_argus.reports.industry_render import (
    profit_opportunities,
    render_csv,
    render_html,
    render_markdown,
    write_reports,
)
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings


@pytest.fixture
def inputs() -> Inputs:
    """Provide one fictional owned BPO and its purchased input."""
    return Inputs(
        items={
            1: Item(type_id=1, name="Input"),
            2: Item(type_id=2, name="Product", group_id=9, group_name="Group"),
            3: Item(type_id=3, name="Blueprint"),
        },
        blueprints={
            3: Blueprint(
                blueprint_id=3,
                product_id=2,
                output=1,
                max_runs=100,
                materials=(Material(type_id=1, quantity=2),),
                manufacturing_seconds=600,
                copying_seconds=60,
            )
        },
        inventions=(),
        originals=(Original(blueprint_id=3, item_id=42, me=10, te=20),),
        reaction_products=set(),
        adjusted_prices={1: Decimal("10")},
        input_prices={1: Decimal("20")},
        indices={"copying": Decimal("0.02"), "manufacturing": Decimal("0.04")},
        markets={},
        sources=[],
        scope="Synthetic",
        system_id=30000142,
        system_name="Jita",
    )


def test_cli_requires_system_and_valid_rates(tmp_path: Path) -> None:
    """Require a system and reject invalid percentages and conflicting selections."""
    runner = CliRunner()
    common = ["reports", "industry", "--to", str(tmp_path)]
    assert runner.invoke(app, [*common, "--help"]).exit_code == 0
    assert runner.invoke(app, common).exit_code == 2
    for flags in (
        ["--system-id", "0"],
        ["--system-id", "123", "--sales-tax", "-1"],
        ["--system-id", "123", "--broker-fee", "101"],
        ["--system-id", "123", "--owned", "--sample"],
    ):
        assert runner.invoke(app, [*common, *flags]).exit_code == 2


def test_cli_generates_linked_outputs_and_keeps_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, inputs: Inputs
) -> None:
    """Use selected settings and options to render one timestamped artifact set."""
    inputs.warnings.append("Synthetic warning")
    read = Mock(return_value=(inputs, (2,)))
    monkeypatch.setattr(command, "read_inputs", read)
    monkeypatch.setattr(command, "get_static_database_path", lambda _: tmp_path / "sde")
    settings = Mock(spec=EveArgusSettings)
    settings.corporation_id = 7
    settings.argus_dynamic_database = tmp_path / "dynamic"
    settings.market_history_database = tmp_path / "history"
    result = CliRunner().invoke(
        app,
        [
            "reports",
            "industry",
            "--system-id",
            "30000142",
            "--to",
            str(tmp_path),
            "--type-id",
            "2",
            "--sales-tax",
            "5",
            "--broker-fee",
            "2",
            "--quiet",
        ],
        obj={SETTINGS_KEY: settings},
    )
    assert result.exit_code == 0, (result.output, result.exception)
    assert "Synthetic warning" in result.output
    assert "Wrote" not in result.output
    assert read.call_args.kwargs["system_id"] == 30000142
    assert read.call_args.kwargs["corporation_id"] == 7
    directory = next(tmp_path.glob("industry-*"))
    with (directory / "industry-report.csv").open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert rows[0]["sales_tax_rate"] == "0.05"
    assert rows[0]["broker_fee_rate"] == "0.02"
    html = (directory / "html" / "index.html").read_text(encoding="utf-8")
    assert "group-9.html" in html
    assert (directory / "html" / "group-9.html").is_file()
    assert (directory / "markdown" / "index.md").is_file()
    assumptions = (directory / "html" / "assumptions.html").read_text(encoding="utf-8")
    assert "Jita" in assumptions
    assert "station service" in assumptions.lower()


def test_history_staleness_boundary(inputs: Inputs) -> None:
    """History receipt age is stale only when greater than the configured duration."""
    from pfmsoft.eve_argus.reports.industry import Source

    received = datetime(2026, 1, 1, tzinfo=UTC)
    source = Source(
        label="History",
        reference="fixture",
        received_at=received.isoformat(),
        history_stale_days=7,
    )
    assert source.freshness(now=received + timedelta(days=7)) == "fresh"
    assert source.freshness(now=received + timedelta(days=7, seconds=1)) == "stale"


def test_fees_and_missing_prices(inputs: Inputs) -> None:
    """Keep cost and sale scenarios precise and leave unknown costs unknown."""
    inputs.markets[60003760, 2] = Market(
        station_id=60003760,
        type_id=2,
        buy=Decimal("1000"),
        sell=Decimal("1000"),
        history_price=Decimal("1000"),
    )
    report = build_report(inputs, product_ids=(2,))
    plan = report.plans[0]
    buy, sell, history = plan.outcomes[:3]
    assert buy.net_per_unit == Decimal("964")
    assert sell.net_per_unit == history.net_per_unit == Decimal("954")
    assert plan.total is not None
    assert plan.total == sum(p.cost for p in plan.shopping) + sum(
        j.total_fee for j in plan.jobs
    )
    assert plan.unit_cost == plan.total / 10
    assert buy.total_profit == (Decimal("964") - plan.unit_cost) * 10
    inputs.input_prices.clear()
    incomplete = build_report(inputs, product_ids=(2,)).plans[0]
    assert incomplete.total is None
    assert all(outcome.total_profit is None for outcome in incomplete.outcomes)
    assert any("Missing Jita" in warning for warning in incomplete.warnings)


def test_blueprint_ties_and_output_safety(tmp_path: Path, inputs: Inputs) -> None:
    """Select one real BPO and preflight all linked files before writing."""
    inputs.originals = (
        Original(blueprint_id=3, item_id=8, me=10, te=4),
        Original(blueprint_id=3, item_id=7, me=10, te=4, quantity=2),
        Original(blueprint_id=3, item_id=9, me=9, te=20),
    )
    report = build_report(inputs, product_ids=(2,))
    copying = next(job for job in report.plans[0].jobs if job.activity == "copying")
    assert (copying.original_item_id, copying.me, copying.te) == (7, 10, 4)
    paths = write_reports(report, destination=tmp_path)
    old = paths[0].read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_reports(report, destination=tmp_path)
    assert paths[0].read_text(encoding="utf-8") == old
    assert write_reports(report, destination=tmp_path, overwrite=True) == paths


def test_cross_format_escape_and_agreement(inputs: Inputs) -> None:
    """Render one model without unescaped HTML or inconsistent CSV amounts."""
    inputs.items[2] = replace(inputs.items[2], name="<script>alert(1)</script>|Product")
    report = build_report(inputs, product_ids=(2,))
    row = next(csv.DictReader(io.StringIO(render_csv(report))))
    assert row["name"] == inputs.items[2].name
    assert Decimal(row["unit_cost"]) == report.plans[0].unit_cost
    assert "<script>" not in render_html(report)
    assert "&lt;script&gt;" in render_html(report)
    markdown = render_markdown(report)
    assert "\\|" in markdown
    from pfmsoft.eve_argus.helpers.markdown import format_markdown

    assert format_markdown(markdown) == markdown


def test_make_or_buy_component_and_copy_splitting(inputs: Inputs) -> None:
    """Make combines component demand, while buy values it at the Jita boundary."""
    inputs.items[4] = Item(type_id=4, name="Component")
    inputs.items[5] = Item(type_id=5, name="Component blueprint")
    inputs.blueprints[3] = replace(
        inputs.blueprints[3], materials=(Material(type_id=4, quantity=2),)
    )
    inputs.blueprints[5] = Blueprint(
        blueprint_id=5,
        product_id=4,
        output=4,
        max_runs=2,
        materials=(Material(type_id=1, quantity=3),),
        manufacturing_seconds=600,
        copying_seconds=60,
    )
    inputs.originals += (Original(blueprint_id=5, item_id=10, me=0, te=0),)
    inputs.adjusted_prices[4] = Decimal("15")
    inputs.input_prices[4] = Decimal("100")
    buy, make = build_report(inputs, product_ids=(2,)).plans
    component = next(node for node in make.nodes if node.type_id == 4)
    assert component.required == 18
    assert component.produced == 20
    assert [
        job.runs
        for job in make.jobs
        if job.activity == "manufacturing" and job.blueprint_id == 5
    ] == [2, 2, 1]
    assert {line.type_id for line in buy.shopping} == {4}
    assert {line.type_id for line in make.shopping} == {1}
    assert make.total == sum(line.cost for line in make.shopping) + sum(
        job.total_fee for job in make.jobs
    )
    assert make.nodes[0].cost == make.total
    inputs.originals = inputs.originals[:1]
    unavailable = build_report(inputs, product_ids=(2,)).plans[1]
    assert unavailable.total is None
    assert any("Missing owned BPO" in warning for warning in unavailable.warnings)


def test_invention_costs_and_t2_ship_batch(inputs: Inputs) -> None:
    """Budget attempts per BPC and use invented runs, not a fictional T2 BPO."""
    inputs.items[6] = Item(type_id=6, name="T2 ship", family="t2-ship-rig")
    inputs.items[7] = Item(type_id=7, name="T2 blueprint")
    inputs.blueprints[7] = Blueprint(
        blueprint_id=7,
        product_id=6,
        output=1,
        max_runs=100,
        materials=(Material(type_id=1, quantity=2),),
        manufacturing_seconds=600,
        copying_seconds=None,
    )
    inputs.inventions = (
        Invention(
            source_blueprint_id=3,
            target_blueprint_id=7,
            base_probability=Decimal("0.3"),
            licensed_runs=1,
            seconds=60,
            materials=(Material(type_id=1, quantity=1),),
        ),
    )
    inputs.indices["invention"] = Decimal("0.03")
    plan = build_report(inputs, product_ids=(6,)).plans[0]
    assert plan.reference_runs == plan.produced == 1
    assert plan.nodes[0].me == 2 and plan.nodes[0].te == 4
    assert plan.nodes[0].attempts_per_bpc == 3
    assert sum(job.runs for job in plan.jobs if job.activity == "invention") == 3
    assert all(job.blueprint_id != 7 for job in plan.jobs if job.activity == "copying")
    assert rounded_attempts(Decimal("0.4")) == 3
    assert plan.total is not None


def test_opportunity_threshold_uses_unrounded_return(inputs: Inputs) -> None:
    """Include the exact 20 percent boundary but not a lower history return."""
    plan = build_report(inputs, product_ids=(2,)).plans[0]
    assert plan.unit_cost is not None
    inputs.markets[60003760, 2] = Market(
        station_id=60003760,
        type_id=2,
        history_price=plan.unit_cost * Decimal("1.2"),
    )
    report = build_report(
        inputs, product_ids=(2,), sales_tax_rate=Decimal(0), broker_fee_rate=Decimal(0)
    )
    assert report.plans[0].outcomes[2].return_pct == 20
    assert len(profit_opportunities(report).tables[0].rows) == 1
    inputs.markets[60003760, 2] = replace(
        inputs.markets[60003760, 2],
        history_price=plan.unit_cost * Decimal("1.199999"),
    )
    report = build_report(
        inputs, product_ids=(2,), sales_tax_rate=Decimal(0), broker_fee_rate=Decimal(0)
    )
    assert not profit_opportunities(report).tables[0].rows


def test_not_owned_uses_hypothetical_research_only_for_missing_bpos(
    inputs: Inputs,
) -> None:
    """Keep actual research and explicitly mark hypothetical blueprint access."""
    inputs.items[4] = Item(type_id=4, name="Unowned product", meta_level=0)
    inputs.items[5] = Item(type_id=5, name="Unowned blueprint")
    inputs.blueprints[5] = replace(inputs.blueprints[3], blueprint_id=5, product_id=4)
    selected = select_bpo_products(
        inputs, published_blueprint_ids={3, 5}, owned=False, me=8, te=16
    )
    assert selected == (4,)
    hypothetical = next(
        original for original in inputs.originals if original.blueprint_id == 5
    )
    assert (hypothetical.item_id, hypothetical.me, hypothetical.te) == (None, 8, 16)
    assert inputs.originals[0].me == 10
    assert any("hypothetical" in warning for warning in inputs.warnings)


def test_render_failure_writes_nothing(
    tmp_path: Path, inputs: Inputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A renderer failure is reported before creating output directories."""

    def fail(_report: object) -> str:
        raise ValueError("renderer failure")

    monkeypatch.setattr(industry_render, "render_csv", fail)
    destination = tmp_path / "report"
    with pytest.raises(ValueError, match="renderer failure"):
        write_reports(build_report(inputs, product_ids=(2,)), destination=destination)
    assert not destination.exists()
