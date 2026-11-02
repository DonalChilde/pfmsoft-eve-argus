"""Contracts for generalized region and system price-summary exports."""

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

from pfmsoft.eve_argus.cli import app
from pfmsoft.eve_argus.dynamic import read, util
from pfmsoft.eve_argus.helpers.file_safe_string import file_safe_string
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS, MarketHub
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings
from pfmsoft.eve_argus.static.store import ManifestEntry, StaticManifest
from pfmsoft.eve_argus.static.util import load_table_definitions

RECEIVED = "2026-10-17T22:07:37.553890662Z"
NAME = 'Mineral, "special"\nvariant'


@dataclass(slots=True, kw_only=True)
class Environment:
    """On-disk local inputs exercised through the registered root CLI."""

    settings: EveArgusSettings
    dynamic_path: Path
    static_path: Path


def populate_static(connection: sqlite3.Connection) -> None:
    """Create static type, market-group, region, and system records."""
    connection.executescript(load_table_definitions())
    connection.execute(
        "INSERT INTO categories (category_id, name, published) VALUES (4, 'Materials', 1)"
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
        VALUES (10, '', 1, 'Minerals', '[10]', '["Minerals"]', '[34,35,37]')"""
    )
    connection.executemany(
        """INSERT INTO types
        (type_id, group_id, market_group_id, name, portion_size, published)
        VALUES (?, 1, ?, ?, 1, ?)""",
        [
            (34, 10, NAME, 1),
            (35, 10, "Unpublished", 0),
            (36, None, "No group", 1),
        ],
    )
    regions = {hub.region_id: hub.region_name for hub in MARKET_HUBS}
    for region_id, region_name in regions.items():
        connection.execute(
            """INSERT INTO map_regions
            (region_id, description, name, nebula_id, position_x, position_y,
             position_z)
            VALUES (?, '', ?, 1, 0, 0, 0)""",
            (region_id, region_name),
        )
    for index, hub in enumerate(MARKET_HUBS):
        constellation_id = 200000 + index
        connection.execute(
            """INSERT INTO map_constellations
            (constellation_id, name, position_x, position_y, position_z, region_id)
            VALUES (?, ?, 0, 0, 0, ?)""",
            (constellation_id, f"{hub.system_name} constellation", hub.region_id),
        )
        connection.execute(
            """INSERT INTO map_solar_systems
            (solar_system_id, constellation_id, name, position_x, position_y,
             position_z, radius, region_id, security_status)
            VALUES (?, ?, ?, 0, 0, 0, 1, ?, 0.9)""",
            (hub.system_id, constellation_id, hub.system_name, hub.region_id),
        )
    connection.commit()


@pytest.fixture
def environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Environment:
    """Set up real databases and forbid network resource initialization."""
    dynamic_path = tmp_path / "dynamic.sqlite"
    static_path = tmp_path / "static.sqlite"
    with closing(sqlite3.connect(dynamic_path)) as connection:
        connection.executescript(util.load_table_definitions())
    with closing(sqlite3.connect(static_path)) as connection:
        populate_static(connection)
    (tmp_path / "manifest.json").write_text(
        StaticManifest(
            entries={
                1: ManifestEntry(
                    build_number=1,
                    release_date="2026-10-17",
                    file_name=static_path.name,
                )
            }
        ).serialize()
    )
    settings = Mock(spec=EveArgusSettings)
    settings.static_database_store = tmp_path
    settings.static_database_build_number = None
    settings.argus_dynamic_database = dynamic_path
    monkeypatch.setattr(
        "pfmsoft.eve_argus.eve_argus.EveArgusResources.__aenter__",
        Mock(side_effect=AssertionError("Export must not initialize ESI resources")),
    )
    return Environment(
        settings=cast(EveArgusSettings, settings),
        dynamic_path=dynamic_path,
        static_path=static_path,
    )


def save(
    env: Environment,
    *,
    hub: MarketHub = MARKET_HUBS[0],
    received_at: str = RECEIVED,
) -> int:
    """Save raw regional orders, including items in other systems."""
    with closing(sqlite3.connect(env.dynamic_path)) as connection:
        source_id = connection.execute(
            "SELECT id FROM response_metadata WHERE received_at = ?",
            (received_at,),
        ).fetchone()
        if source_id is None:
            source_id = (
                connection.execute(
                    "INSERT INTO response_metadata (received_at, expires_at) VALUES (?, ?)",
                    (received_at, "2026-10-18T00:00:00Z"),
                ).lastrowid,
            )
        metadata_id = source_id[0]
        assert isinstance(metadata_id, int)
        connection.execute(
            """INSERT OR IGNORE INTO get_markets_region_id_orders_response
            (response_metadata_id, region_id, received_at) VALUES (?, ?, ?)""",
            (metadata_id, hub.region_id, received_at),
        )
        rows = [
            (34, 1, 10000, 100, hub.system_id, hub.station_id),
            (34, 1, 9000, 20, hub.system_id, hub.station_id + 1),
            (34, 1, 1, 5, hub.system_id, hub.station_id),
            (34, 0, 11000, 100, hub.system_id, hub.station_id),
            (34, 0, 2000000, 5, hub.system_id, hub.station_id),
            (35, 1, 10000, 10, hub.system_id, hub.station_id),
            (36, 0, 11000, 10, hub.system_id, hub.station_id),
            (999, 1, 10000, 10, hub.system_id + 1, hub.station_id + 2),
        ]
        connection.executemany(
            """
            INSERT INTO market_orders (
                response_metadata_id, region_id, duration, is_buy_order,
                issued, location_id, min_volume, order_id, price, range_,
                system_id, type_id, volume_remain, volume_total
            ) VALUES (?, ?, 90, ?, ?, ?, 1, ?, ?, 'station', ?, ?, ?, ?)
            """,
            [
                (
                    metadata_id,
                    hub.region_id,
                    buy,
                    received_at,
                    station_id,
                    order_id,
                    cents,
                    system_id,
                    type_id,
                    items,
                    items,
                )
                for order_id, (
                    type_id,
                    buy,
                    cents,
                    items,
                    system_id,
                    station_id,
                ) in enumerate(rows, start=1)
            ],
        )
        connection.commit()
        return metadata_id


def invoke_price_summaries(env: Environment, destination: Path, *args: str) -> Result:
    """Run generalized price-summaries with real SQLite readers."""
    return CliRunner().invoke(
        app,
        ["reports", "price-summaries", "--to", str(destination), *args],
        obj={SETTINGS_KEY: env.settings},
    )


def save_all(env: Environment) -> None:
    """Give each hub a distinct source timestamp."""
    for index, hub in enumerate(MARKET_HUBS):
        save(env, hub=hub, received_at=f"2026-10-17T22:07:3{index}.553890662Z")


def test_price_summaries_region_and_system_are_distinct_scopes(
    environment: Environment,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deduplicate repeated IDs while exporting region and system scopes separately."""
    hub = MARKET_HUBS[0]
    save(environment, hub=hub)
    load_orders = Mock(wraps=read.market_orders)
    monkeypatch.setattr(read, "market_orders", load_orders)
    with closing(sqlite3.connect(environment.static_path)) as connection:
        connection.execute(
            """INSERT INTO types
            (type_id, group_id, name, portion_size, published)
            VALUES (999, 1, 'Other system item', 1, 1)"""
        )
        connection.commit()
    destination = tmp_path / "scopes"
    result = invoke_price_summaries(
        environment,
        destination,
        "--region-id",
        str(hub.region_id),
        "--region-id",
        str(hub.region_id),
        "--system-id",
        str(hub.system_id),
        "--system-id",
        str(hub.system_id),
        "--filter-factor",
        "10",
        "--quiet",
    )
    assert result.exit_code == 0, result.output
    timestamp = file_safe_string(RECEIVED)
    region_path = (
        destination
        / f"price-summary-{file_safe_string(hub.region_name)}-{timestamp}.json"
    )
    system_path = (
        destination
        / f"price-summary-{file_safe_string(hub.system_name)}-{timestamp}.json"
    )
    region_report = json.loads(region_path.read_text())
    system_report = json.loads(system_path.read_text())
    assert len(list(destination.iterdir())) == 4
    assert load_orders.call_count == 1
    assert region_report["schema_version"] == system_report["schema_version"] == 2
    assert region_report["scope"] == "region"
    assert region_report["region_id"] == hub.region_id
    assert region_report["region_name"] == hub.region_name
    assert region_report["system_id"] is None
    assert region_report["system_name"] is None
    assert region_report["filter_factor"] == "10"
    assert 999 in {row["type_id"] for row in region_report["records"]}
    region_csv = list(
        csv.DictReader(StringIO(region_path.with_suffix(".csv").read_text()))
    )
    assert [int(row["type_id"]) for row in region_csv] == [
        row["type_id"] for row in region_report["records"]
    ]
    assert {row["filter_factor"] for row in region_csv} == {"10"}
    assert system_report["scope"] == "system"
    assert system_report["system_id"] == hub.system_id
    assert system_report["system_name"] == hub.system_name
    assert 999 not in {row["type_id"] for row in system_report["records"]}


def test_price_summaries_system_only_and_hubs_are_deduplicated(
    environment: Environment, tmp_path: Path
) -> None:
    """Resolve system-only regions and deduplicate explicit scopes against --hubs."""
    save_all(environment)
    destination = tmp_path / "system-only"
    result = invoke_price_summaries(
        environment, destination, "--system-id", str(MARKET_HUBS[0].system_id)
    )
    assert result.exit_code == 0, result.output
    system_json = next(destination.glob("*.json"))
    system_report = json.loads(system_json.read_text())
    assert system_report["region_id"] == MARKET_HUBS[0].region_id
    assert system_report["system_id"] == MARKET_HUBS[0].system_id
    assert system_json.name.startswith("price-summary-Jita-")

    original_json = system_json.read_bytes()
    collision = invoke_price_summaries(
        environment, destination, "--system-id", str(MARKET_HUBS[0].system_id)
    )
    assert collision.exit_code == 1
    assert "--overwrite" in collision.output
    assert system_json.read_bytes() == original_json
    overwritten = invoke_price_summaries(
        environment,
        destination,
        "--system-id",
        str(MARKET_HUBS[0].system_id),
        "--overwrite",
        "--quiet",
    )
    assert overwritten.exit_code == 0, overwritten.output

    with closing(sqlite3.connect(environment.static_path)) as connection:
        connection.execute(
            """INSERT INTO types
            (type_id, group_id, name, portion_size, published)
            VALUES (999, 1, 'Other system item', 1, 1)"""
        )
        connection.commit()
    hubs_destination = tmp_path / "with-hubs"
    result = invoke_price_summaries(
        environment,
        hubs_destination,
        "--system-id",
        str(MARKET_HUBS[0].system_id),
        "--region-id",
        str(MARKET_HUBS[0].region_id),
        "--hubs",
        "--quiet",
    )
    assert result.exit_code == 0, result.output
    assert len(list(hubs_destination.iterdir())) == 12
    assert len(list(hubs_destination.glob("price-summary-Jita-*.json"))) == 1
    assert len(list(hubs_destination.glob("price-summary-The_Forge-*.json"))) == 1


def test_price_summaries_validation_and_missing_snapshot(
    environment: Environment, tmp_path: Path
) -> None:
    """Reject missing/invalid selections and show actionable fetch guidance."""
    runner = CliRunner()
    no_selection = runner.invoke(
        app,
        ["reports", "price-summaries", "--to", str(tmp_path / "none")],
        obj={SETTINGS_KEY: environment.settings},
    )
    assert no_selection.exit_code == 2
    assert "--region-id" in no_selection.output

    invalid_factor = invoke_price_summaries(
        environment,
        tmp_path / "invalid-factor",
        "--region-id",
        str(MARKET_HUBS[0].region_id),
        "--filter-factor",
        "1",
    )
    assert invalid_factor.exit_code == 2
    assert "--filter-factor" in invalid_factor.output

    unknown_system = invoke_price_summaries(
        environment,
        tmp_path / "unknown-system",
        "--system-id",
        "999999999",
    )
    assert unknown_system.exit_code == 2
    assert "Unknown or invalid system ID" in unknown_system.output

    missing_hub = MARKET_HUBS[1]
    save(environment, hub=MARKET_HUBS[0])
    missing = invoke_price_summaries(
        environment,
        tmp_path / "missing",
        "--system-id",
        str(missing_hub.system_id),
        "--quiet",
    )
    assert missing.exit_code == 1
    assert missing_hub.region_name in missing.output
    assert f"fetch market-orders --region-id {missing_hub.region_id}" in missing.output
    assert not (tmp_path / "missing").exists()
