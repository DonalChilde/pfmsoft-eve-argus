"""Tests for the provisional ME research comparison, not verified game rules."""

import csv
import json
import runpy
import sqlite3
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "dev/proof-scripts/industry-research/compare_me_research.py"
)


@pytest.fixture
def proof():
    """Load the proof without invoking its command-line entry point."""
    return runpy.run_path(str(SCRIPT))


def test_candidate_agreement_and_step_boundaries(proof):
    """Rank-one candidates agree; totals accumulate separately rounded jobs."""
    rows = proof["calculate_rows"](
        manufacturing_eiv=Decimal("1000"),
        base_time_seconds=105,
        system_cost_index=Decimal("0.0525"),
        facility_tax_rate=Decimal("0.0025"),
        scc_rate=Decimal("0.02"),
        alpha_tax_rate=Decimal("0.0025"),
    )
    assert len(rows) == 30
    for candidate in {row["candidate"] for row in rows}:
        steps = [row for row in rows if row["candidate"] == candidate]
        assert [row["start_me"] for row in steps] == list(range(10))
        assert [row["target_me"] for row in steps] == list(range(1, 11))
        assert sum(row["base_step_seconds"] for row in steps) == 256000
        assert steps[0]["ptv_raw_isk"] == Decimal("20")
        assert steps[0]["total_raw_isk"] == Decimal("1.55")
        assert steps[-1]["cumulative_total_components_cents_isk"] == sum(
            row["total_components_cents_isk"] for row in steps
        )


def test_non_rank_one_and_ptv_ceiling(proof):
    """A synthetic rank-two case distinguishes fixed-reference normalization."""
    rows = proof["calculate_rows"](
        manufacturing_eiv=Decimal("1001"),
        base_time_seconds=210,
        system_cost_index=Decimal("0.0525"),
        facility_tax_rate=Decimal("0.0025"),
        scc_rate=Decimal("0.02"),
        alpha_tax_rate=Decimal("0"),
    )
    first = {row["candidate"]: row for row in rows if row["target_me"] == 1}
    assert first["level_multiplier"]["ptv_raw_isk"] == Decimal("20.02")
    assert first["blueprint_time_normalized"]["ptv_raw_isk"] == Decimal("20.02")
    assert first["fixed_105_seconds"]["ptv_raw_isk"] == Decimal("40.04")
    assert first["level_multiplier"]["ptv_ceiling_isk"] == Decimal("21")
    assert first["level_multiplier"]["alpha_raw_isk"] == 0


def test_zero_to_target_job_rounding(proof):
    """Zero-to-target PTV and fees use one job boundary, not rounded step sums."""
    inputs = {
        "manufacturing_eiv": Decimal("1457.96"),
        "base_time_seconds": 105,
        "system_cost_index": Decimal("0.0525"),
        "facility_tax_rate": Decimal("0.0025"),
        "scc_rate": Decimal("0.02"),
        "alpha_tax_rate": Decimal("0.0025"),
    }
    rows = proof["calculate_rows"](**inputs, from_zero=True)
    incremental = proof["calculate_rows"](**inputs)
    assert len(rows) == 30
    for candidate in {row["candidate"] for row in rows}:
        jobs = [row for row in rows if row["candidate"] == candidate]
        assert [row["start_me"] for row in jobs] == [0] * 10
        assert [row["target_me"] for row in jobs] == list(range(1, 11))
        assert [row["base_step_seconds"] for row in jobs] == [
            Decimal(value) for value in proof["CUMULATIVE_SECONDS"][1:]
        ]
        assert (
            jobs[1]["ptv_raw_isk"] == Decimal("1457.96") * Decimal("0.02") * 250 / 105
        )
        assert jobs[1]["total_components_cents_isk"] == Decimal("5.37")
        assert jobs[2]["total_components_cents_isk"] == Decimal("12.79")
        assert jobs[9]["gross_job_cost_whole_isk"] == Decimal("3732")
        assert jobs[9]["total_taxes_whole_isk"] == Decimal("1778")
        assert jobs[9]["total_job_cost_whole_isk"] == Decimal("5510")
        assert (
            jobs[2]["total_components_cents_isk"]
            != (incremental[2]["cumulative_total_components_cents_isk"])
        )
        assert all(
            job["cumulative_total_components_cents_isk"]
            == job["total_components_cents_isk"]
            for job in jobs
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"base_time_seconds": 0},
        {"manufacturing_eiv": Decimal("-1")},
        {"system_cost_index": Decimal("NaN")},
        {"facility_tax_rate": Decimal("-0.1")},
    ],
)
def test_invalid_inputs(proof, overrides):
    """Invalid numeric inputs fail instead of producing successful estimates."""
    inputs = {
        "manufacturing_eiv": Decimal("1000"),
        "base_time_seconds": 105,
        "system_cost_index": Decimal("0.0525"),
        "facility_tax_rate": Decimal("0.0025"),
        "scc_rate": Decimal("0.02"),
        "alpha_tax_rate": Decimal("0.0025"),
    }
    with pytest.raises(ValueError):
        proof["calculate_rows"](**(inputs | overrides))


def test_export_csv_matches_json(proof, tmp_path):
    """Exported monetary strings agree, with independent baseline and job tables."""
    rows = proof["calculate_rows"](
        manufacturing_eiv=Decimal("1000"),
        base_time_seconds=105,
        system_cost_index=Decimal("0.0525"),
        facility_tax_rate=Decimal("0.0025"),
        scc_rate=Decimal("0.02"),
        alpha_tax_rate=Decimal("0.0025"),
    )
    proof["export_results"](
        output_dir=tmp_path, metadata={"status": "provisional"}, rows=rows
    )
    document = json.loads((tmp_path / "me_research.json").read_text())
    with (tmp_path / "me_research.csv").open(newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    assert document["metadata"]["status"] == "provisional"
    assert len(document["steps"]) == len(csv_rows) == 30
    for json_row, csv_row in zip(document["steps"], csv_rows, strict=True):
        assert csv_row == {key: str(value) for key, value in json_row.items()}


def test_main_help_does_not_open_database(proof):
    """Help exits before reading any database."""
    with patch("sys.argv", [str(SCRIPT), "--help"]):
        with pytest.raises(SystemExit) as exc:
            proof["main"]()
    assert exc.value.code == 0


def test_snapshot_loading_and_missing_price(proof, tmp_path):
    """Mock dataset readers while exercising actual read-only SQLite connections."""
    from pfmsoft.eve_argus.dynamic import read as dynamic_read
    from pfmsoft.eve_argus.dynamic.models import MarketsPricesResponse
    from pfmsoft.eve_argus.static import read as static_read

    database = tmp_path / "input.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sentinel (value INTEGER)")
    response = MarketsPricesResponse(
        response_metadata_id=1,
        received_at="2026-10-27T19:33:05Z",
        expires_at=None,
        argus_expires_at=None,
    )
    activity = SimpleNamespace(
        time=105, materials=(SimpleNamespace(type_id=34, quantity=204),)
    )
    blueprint = SimpleNamespace(
        activities=SimpleNamespace(
            manufacturing=activity,
            research_material=SimpleNamespace(time=105, materials=()),
        )
    )
    price = SimpleNamespace(adjusted_price=Decimal("3.14"))
    inputs = {
        "static_database": database,
        "dynamic_database": database,
        "blueprint_name": "Antimatter Charge S Blueprint",
        "system_name": "Osmeden",
    }
    with (
        patch.object(
            static_read,
            "types",
            return_value={
                1137: SimpleNamespace(
                    type_id=1137, name="Antimatter Charge S Blueprint"
                ),
                34: SimpleNamespace(type_id=34, name="Tritanium"),
            },
        ),
        patch.object(static_read, "blueprints", return_value={1137: blueprint}),
        patch.object(
            static_read,
            "map_solar_systems",
            return_value={
                30003831: SimpleNamespace(solar_system_id=30003831, name="Osmeden")
            },
        ),
        patch.object(dynamic_read, "markets_prices_responses", return_value=[response]),
        patch.object(
            dynamic_read, "system_cost_indices_responses", return_value=[response]
        ),
        patch.object(
            dynamic_read,
            "markets_prices",
            return_value=SimpleNamespace(records={34: price}),
        ),
        patch.object(
            dynamic_read,
            "system_cost_indices",
            return_value=SimpleNamespace(
                records={
                    30003831: SimpleNamespace(
                        researching_material_efficiency=Decimal("0.0525")
                    )
                }
            ),
        ),
        patch("sqlite3.connect", wraps=sqlite3.connect) as connect,
    ):
        result = proof["load_inputs"](**inputs)
        assert result.manufacturing_eiv == Decimal("640.56")
        assert result.base_time_seconds == 105
        assert result.system_cost_index == Decimal("0.0525")
        assert len(connect.call_args_list) == 2
        for call in connect.call_args_list:
            assert call.args[0].endswith("?mode=ro")
            assert call.kwargs == {"uri": True}
        price.adjusted_price = None
        with pytest.raises(ValueError, match="Missing adjusted price"):
            proof["load_inputs"](**inputs)


def test_main_exports_scenario(proof, tmp_path):
    """CLI uses resolved snapshots and records explicit assumptions."""
    inputs = proof["SnapshotInputs"](
        manufacturing_eiv=Decimal("1000"),
        base_time_seconds=105,
        system_cost_index=Decimal("0.0525"),
        metadata={"blueprint_type_id": 1137},
    )
    with (
        patch(
            "sys.argv",
            [
                str(SCRIPT),
                "--static-database",
                "unused.sqlite",
                "--output-dir",
                str(tmp_path),
            ],
        ),
        patch.dict(proof["main"].__globals__, {"load_inputs": lambda **kwargs: inputs}),
    ):
        proof["main"]()
    document = json.loads((tmp_path / "me_research.json").read_text())
    assert len(document["steps"]) == 30
    assert document["metadata"]["blueprint_type_id"] == 1137
    assert document["steps"][0]["scc_rate"] == "0.02"
    assert all(row["start_me"] == 0 for row in document["steps"])
    incremental = json.loads((tmp_path / "incremental/me_research.json").read_text())
    assert incremental["steps"][1]["start_me"] == 1
