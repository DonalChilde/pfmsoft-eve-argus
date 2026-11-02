"""Contracts for per-region stored market-history summary reports."""

import csv
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner, Result
from whenever import Instant

from pfmsoft.eve_argus.cli import app
from pfmsoft.eve_argus.cli.reports import history_summary as command
from pfmsoft.eve_argus.helpers.file_safe_string import file_safe_string
from pfmsoft.eve_argus.market_history import util as history_util
from pfmsoft.eve_argus.market_history.helpers import first_possible_date
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings
from pfmsoft.eve_argus.static.util import load_table_definitions as static_definitions

REGION_ID = MARKET_HUBS[0].region_id
REGION_NAME = MARKET_HUBS[0].region_name
RECEIVED_RECENT = "2026-10-21T12:00:00Z"
RECEIVED_OLD = "2026-10-02T12:00:00Z"


@dataclass(slots=True, kw_only=True)
class ReportEnvironment:
    """Synthetic history and static databases for command integration tests."""

    settings: EveArgusSettings
    history_path: Path
    static_path: Path


def _insert_history(
    connection: sqlite3.Connection,
    *,
    type_id: int,
    day: str,
    received_at: str,
    average: int,
    highest: int,
    lowest: int,
    order_count: int,
    volume: int,
    argus_expires_at: str | None = None,
) -> None:
    """Insert a daily history record; prices are stored as cents."""
    connection.execute(
        """INSERT INTO market_history (
            received_at, expires_at, argus_expires_at, region_id, type_id,
            average, date_, highest, lowest, order_count, volume
        ) VALUES (?, '2099-01-01T00:00:00Z', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            received_at,
            argus_expires_at,
            REGION_ID,
            type_id,
            average,
            day,
            highest,
            lowest,
            order_count,
            volume,
        ),
    )


@pytest.fixture
def environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ReportEnvironment:
    """Create databases with two types, one complete market path, and history rows."""
    history_path = tmp_path / "market-history.sqlite"
    static_path = tmp_path / "static.sqlite"
    with closing(sqlite3.connect(history_path)) as connection:
        connection.executescript(history_util.load_table_definitions())
        _insert_history(
            connection,
            type_id=34,
            day="2026-10-20",
            received_at=RECEIVED_RECENT,
            average=206,
            highest=300,
            lowest=100,
            order_count=4,
            volume=30,
            argus_expires_at="2026-10-20T00:00:00Z",
        )
        _insert_history(
            connection,
            type_id=34,
            day="2026-10-18",
            received_at=RECEIVED_RECENT,
            average=400,
            highest=500,
            lowest=300,
            order_count=7,
            volume=10,
            argus_expires_at="2026-10-20T00:00:00Z",
        )
        _insert_history(
            connection,
            type_id=35,
            day="2026-10-01",
            received_at=RECEIVED_OLD,
            average=100,
            highest=100,
            lowest=100,
            order_count=1,
            volume=2,
        )
        connection.commit()

    with closing(sqlite3.connect(static_path)) as connection:
        connection.executescript(static_definitions())
        connection.execute(
            "INSERT INTO categories (category_id, name, published) "
            "VALUES (4, 'Materials', 1)"
        )
        connection.execute(
            """INSERT INTO groups
            (group_id, anchorable, anchored, category_id, fittable_non_singleton,
             name, published, use_base_price)
            VALUES (1, 0, 0, 4, 0, 'Minerals', 1, 0)"""
        )
        connection.execute(
            """INSERT INTO market_groups
            (market_group_id, description, has_types, name, int_path, str_path, types)
            VALUES (10, '', 1, 'Minerals', '[10]', '["Minerals"]', '[34]')"""
        )
        connection.executemany(
            """INSERT INTO types
            (type_id, group_id, market_group_id, name, portion_size, published)
            VALUES (?, 1, ?, ?, 1, 1)""",
            [(34, 10, "Tritanium"), (35, None, "Pyerite")],
        )
        for region_id, region_name in {
            hub.region_id: hub.region_name for hub in MARKET_HUBS
        }.items():
            connection.execute(
                """INSERT INTO map_regions
                (region_id, description, name, nebula_id, position_x, position_y,
                 position_z)
                VALUES (?, '', ?, 1, 0, 0, 0)""",
                (region_id, region_name),
            )
        connection.commit()

    settings = Mock(spec=EveArgusSettings)
    settings.market_history_database = history_path
    monkeypatch.setattr(
        command, "get_static_database_path", lambda _settings: static_path
    )
    return ReportEnvironment(
        settings=cast(EveArgusSettings, settings),
        history_path=history_path,
        static_path=static_path,
    )


def invoke(environment: ReportEnvironment, destination: Path, *args: str) -> Result:
    """Run the registered report command with synthetic configured settings."""
    return CliRunner().invoke(
        app,
        ["reports", "history-summary", "--to", str(destination), *args],
        obj={SETTINGS_KEY: environment.settings},
    )


def test_history_summary_formats_keep_window_and_market_path(
    environment: ReportEnvironment, tmp_path: Path
) -> None:
    """Emit exact per-type metrics and retain metadata for an empty window."""
    destination = tmp_path / "reports"
    result = invoke(
        environment,
        destination,
        "--region-id",
        str(REGION_ID),
        "--period",
        "3",
        "--start-date",
        "2026-10-20",
        "--quiet",
    )
    assert result.exit_code == 0, result.output
    assert "Warning" in result.output
    assert "Tritanium (34)" in result.output
    json_path = next(destination.glob("history-summary-The_Forge-3d-2026-10-20-*.json"))
    csv_path = json_path.with_suffix(".csv")
    report = json.loads(json_path.read_text())
    assert report["schema_version"] == 1
    assert report["report"] == "history-summary"
    assert report["region_id"] == REGION_ID
    assert report["region_name"] == REGION_NAME
    assert report["period_days"] == 3
    assert report["start_date"] == "2026-10-20"
    assert [row["type_id"] for row in report["records"]] == [34, 35]

    tritanium, pyerite = report["records"]
    assert tritanium["newest_date"] == "2026-10-20"
    assert tritanium["oldest_date"] == "2026-10-18"
    assert tritanium["missing_days"] == 1
    assert tritanium["highest_price"] == "3.50"
    assert tritanium["average_price"] == "2.55"
    assert tritanium["lowest_price"] == "1.50"
    assert tritanium["average_daily_order_count"] == 3
    assert tritanium["average_daily_volume"] == "13.33333333333333333333333333"
    assert tritanium["argus_expires_at"] == "2026-10-20T00:00:00Z"
    assert tritanium["is_stale"] is True
    assert tritanium["market_group_id"] == 10
    assert tritanium["market_group_name"] == "Minerals"
    assert tritanium["market_path_ids"] == [10]
    assert tritanium["market_path_names"] == ["Minerals"]

    assert pyerite["newest_date"] == "2026-10-20"
    assert pyerite["oldest_date"] == "2026-10-18"
    assert pyerite["missing_days"] == 3
    assert pyerite["highest_price"] is None
    assert pyerite["average_price"] is None
    assert pyerite["average_daily_order_count"] is None
    assert pyerite["average_daily_volume"] is None
    assert pyerite["received_at"] == RECEIVED_OLD
    assert pyerite["expires_at"] == "2099-01-01T00:00:00Z"
    assert pyerite["is_stale"] is False
    assert pyerite["market_group_id"] is None
    assert pyerite["market_path_ids"] is None

    csv_rows = list(csv.DictReader(StringIO(csv_path.read_text())))
    assert [int(row["type_id"]) for row in csv_rows] == [34, 35]
    assert csv_rows[0]["average_price"] == "2.55"
    assert csv_rows[0]["market_path_ids"] == "10"
    assert csv_rows[1]["average_price"] == ""
    assert csv_rows[1]["received_at"] == RECEIVED_OLD
    assert csv_rows[1]["market_path_ids"] == ""
    assert file_safe_string(report["generated_at"]) in json_path.name


def test_history_summary_default_uses_per_type_windows(
    environment: ReportEnvironment, tmp_path: Path
) -> None:
    """Without --start-date, each type's latest request yields its own date window."""
    result = invoke(
        environment,
        tmp_path / "reports",
        "--region-id",
        str(REGION_ID),
        "--period",
        "2",
    )
    assert result.exit_code == 0, result.output
    report = json.loads(next((tmp_path / "reports").glob("*.json")).read_text())
    assert report["start_date"] is None
    rows = {row["type_id"]: row for row in report["records"]}
    assert rows[34]["newest_date"] == first_possible_date(RECEIVED_RECENT)
    assert rows[35]["newest_date"] == first_possible_date(RECEIVED_OLD)
    assert rows[34]["newest_date"] != rows[35]["newest_date"]


def test_history_summary_hubs_adds_regions_and_deduplicates(
    environment: ReportEnvironment, tmp_path: Path
) -> None:
    """The hub flag adds distinct configured regions to explicit selections."""
    destination = tmp_path / "hubs"
    result = invoke(
        environment,
        destination,
        "--region-id",
        str(REGION_ID),
        "--hubs",
        "--quiet",
    )
    assert result.exit_code == 0, result.output
    assert len(list(destination.glob("*.json"))) == len(
        {hub.region_id for hub in MARKET_HUBS}
    )
    assert len(list(destination.glob("history-summary-The_Forge-*.json"))) == 1
    assert "no stored market history" in result.output
    for hub in MARKET_HUBS[1:]:
        empty_json = next(
            destination.glob(
                f"history-summary-{file_safe_string(hub.region_name)}-*.json"
            )
        )
        assert json.loads(empty_json.read_text())["records"] == []
        assert (
            len(
                list(
                    csv.DictReader(StringIO(empty_json.with_suffix(".csv").read_text()))
                )
            )
            == 0
        )


def test_history_summary_validation_and_overwrite(
    environment: ReportEnvironment,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Require a selection and protect existing output unless overwrite is set."""
    no_selection = CliRunner().invoke(
        app,
        ["reports", "history-summary", "--to", str(tmp_path / "none")],
        obj={SETTINGS_KEY: environment.settings},
    )
    assert no_selection.exit_code == 2
    assert "--region-id" in no_selection.output

    invalid_date = invoke(
        environment,
        tmp_path / "invalid-date",
        "--region-id",
        str(REGION_ID),
        "--start-date",
        "not-a-date",
    )
    assert invalid_date.exit_code == 2
    assert "--start-date" in invalid_date.output

    destination = tmp_path / "overwrite"
    monkeypatch.setattr(
        command,
        "Instant",
        Mock(now=Mock(return_value=Instant.parse_iso("2026-11-02T18:00:00Z"))),
    )
    result = invoke(environment, destination, "--region-id", str(REGION_ID), "--quiet")
    assert result.exit_code == 0, result.output
    json_path = next(destination.glob("*.json"))
    original = json_path.read_bytes()
    collision = invoke(
        environment, destination, "--region-id", str(REGION_ID), "--quiet"
    )
    assert collision.exit_code == 1
    assert "--overwrite" in collision.output
    assert json_path.read_bytes() == original
    replaced = invoke(
        environment,
        destination,
        "--region-id",
        str(REGION_ID),
        "--overwrite",
        "--quiet",
    )
    assert replaced.exit_code == 0, replaced.output
