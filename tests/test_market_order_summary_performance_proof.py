"""Offline acceptance tests for the market-order summary timing proof."""

import importlib
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from statistics import median
from types import ModuleType

import pytest

from pfmsoft.eve_argus.dynamic import util


@pytest.fixture
def proof(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import the proof without running it or opening application resources."""
    directory = Path(__file__).resolve().parents[1] / "dev/proof-scripts"
    monkeypatch.setattr(sys, "path", [str(directory), *sys.path])
    return importlib.import_module("market_order_summary_performance")


@pytest.fixture
def connection() -> Iterator[sqlite3.Connection]:
    """Create two snapshots with duplicate types, both sides, and distinct scopes."""
    with closing(sqlite3.connect(":memory:")) as database:
        database.executescript(util.load_table_definitions())
        database.executemany(
            "INSERT INTO response_metadata (received_at) VALUES (?)",
            [("2026-10-25T00:00:00Z",), ("2026-10-26T00:00:00Z",)],
        )
        database.executemany(
            """
            INSERT INTO get_markets_region_id_orders_response
                (response_metadata_id, region_id, received_at)
            VALUES (?, 10000002, ?)
            """,
            [(1, "2026-10-25T00:00:00Z"), (2, "2026-10-26T00:00:00Z")],
        )
        database.executemany(
            """
            INSERT INTO market_orders (
                response_metadata_id, region_id, duration, is_buy_order, issued,
                location_id, min_volume, order_id, price, range_, system_id,
                type_id, volume_remain, volume_total
            ) VALUES (?, 10000002, 90, ?, '2026-10-26T00:00:00Z',
                      ?, 1, ?, ?, 'station', ?, ?, ?, ?)
            """,
            [
                (1, 1, 60003760, 1, 99900, 30000142, 99, 1, 1),
                (2, 1, 60003760, 2, 10000, 30000142, 34, 10, 10),
                (2, 1, 60003761, 3, 9000, 30000142, 34, 20, 20),
                (2, 0, 60003760, 4, 11000, 30000142, 34, 10, 10),
                (2, 0, 60003762, 5, 20000, 30000143, 35, 5, 5),
                (2, 1, 60003760, 6, 30000, 30000142, 36, 0, 1),
            ],
        )
        database.commit()
        yield database


@pytest.mark.parametrize(
    ("scope", "type_count"),
    [({}, 3), ({"system_id": 30000142}, 2), ({"location_id": 60003762}, 1)],
)
def test_benchmark_matches_summaries_and_alternates_order(
    proof: ModuleType,
    connection: sqlite3.Connection,
    scope: dict[str, int],
    type_count: int,
) -> None:
    """Compare exact results, including missing sides and zero-volume books."""
    result = proof.benchmark(
        connection,
        options=proof.Options(response_metadata_id=2, repeats=2, **scope),
    )

    assert result["type_count"] == type_count
    assert result["on_demand_calls_per_run"] == type_count
    assert result["verified_equal"] is True
    assert result["sampled"] is False
    assert result["execution_orders"] == [
        ["dataset", "on_demand", "filtered_dataset"],
        ["filtered_dataset", "on_demand", "dataset"],
    ]
    for method in ("dataset", "on_demand", "filtered_dataset"):
        assert len(result["runs"][method]) == 2
        for run in result["runs"][method]:
            assert run["setup_seconds"] >= 0
            assert run["calculation_seconds"] >= 0
            assert run["total_seconds"] == (
                run["setup_seconds"] + run["calculation_seconds"]
            )
        assert result["medians"][method]["total_seconds"] > 0
        for stage in ("setup_seconds", "calculation_seconds", "total_seconds"):
            assert result["medians"][method][stage] == median(
                run[stage] for run in result["runs"][method]
            )
    dataset_total = result["medians"]["dataset"]["total_seconds"]
    demand_total = result["medians"]["on_demand"]["total_seconds"]
    assert result["on_demand_total_ratio"] == demand_total / dataset_total
    assert result["on_demand_extra_seconds"] == demand_total - dataset_total
    assert result["on_demand_seconds_per_call"] == (
        result["medians"]["on_demand"]["calculation_seconds"] / type_count
    )
    assert result["market_order_indexes"] == ["market_orders_response_type_order"]
    assert any(
        "SEARCH market_orders USING INDEX" in row
        for row in result["on_demand_query_plan"]
    )
    assert not any("TEMP B-TREE" in row for row in result["on_demand_query_plan"])


def test_limit_is_explicit_and_uses_sorted_scoped_types(
    proof: ModuleType, connection: sqlite3.Connection
) -> None:
    """A smoke run limits both calculation paths, but still loads the full snapshot."""
    result = proof.benchmark(
        connection,
        options=proof.Options(response_metadata_id=2, repeats=1, limit_types=1),
    )

    assert result["selected_type_ids"] == [34]
    assert result["available_type_count"] == 3
    assert result["type_count"] == 1
    assert result["sampled"] is True
    assert result["snapshot_order_count"] == 5
    assert result["verified_equal"] is True


def test_mismatch_fails_instead_of_reporting_a_comparison(
    proof: ModuleType,
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful-looking timing report must not hide different summary values."""

    def missing_summary(*_args: object, **_kwargs: object) -> tuple[None, None]:
        return None, None

    monkeypatch.setattr(proof.read, "calculate_market_order_summary", missing_summary)
    with pytest.raises(ValueError, match="Summary mismatch"):
        proof.benchmark(
            connection, options=proof.Options(response_metadata_id=2, repeats=1)
        )


@pytest.mark.parametrize(
    "options",
    [
        {"repeats": 0},
        {"limit_types": 0},
        {"system_id": 1, "location_id": 2},
        {"response_metadata_id": 999},
        {"system_id": 999},
    ],
)
def test_invalid_or_empty_inputs_fail(
    proof: ModuleType, connection: sqlite3.Connection, options: dict[str, int]
) -> None:
    """Reject invalid comparisons rather than timing an empty workload."""
    values = {"response_metadata_id": 2, "repeats": 1, **options}
    with pytest.raises(ValueError):
        proof.benchmark(connection, options=proof.Options(**values))


@pytest.mark.parametrize("factor", ["1", "NaN", "Infinity"])
def test_invalid_filter_factors_fail(
    proof: ModuleType, connection: sqlite3.Connection, factor: str
) -> None:
    """Reject nonfinite or ineffective filters before timing the workload."""
    with pytest.raises(ValueError, match="filter_factor"):
        proof.benchmark(
            connection,
            options=proof.Options(
                response_metadata_id=2, filter_factor=Decimal(factor)
            ),
        )


def test_read_only_connection_cannot_create_or_change_database(
    proof: ModuleType, tmp_path: Path
) -> None:
    """The proof must not create a missing database or mutate an existing one."""
    path = tmp_path / "orders.sqlite"
    with pytest.raises(sqlite3.OperationalError):
        proof.open_database(path)
    assert not path.exists()
    with closing(sqlite3.connect(path)) as database:
        database.execute("CREATE TABLE marker (value INTEGER)")
    with closing(proof.open_database(path)) as database:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            database.execute("INSERT INTO marker VALUES (1)")


def test_help_does_not_open_database(
    proof: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI help exits before acquiring database resources."""
    monkeypatch.setattr(sys, "argv", ["proof", "--help"])
    with pytest.raises(SystemExit) as error:
        proof.main()
    assert error.value.code == 0
    assert "--limit-types" in capsys.readouterr().out
