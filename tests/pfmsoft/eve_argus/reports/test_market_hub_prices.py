"""Contracts for offline system-scoped market hub price exports."""

import csv
import json
import sqlite3
from contextlib import AbstractContextManager, closing
from dataclasses import dataclass, replace
from decimal import Decimal
from io import StringIO, TextIOWrapper
from pathlib import Path
from typing import Literal
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner, Result
from whenever import Instant

from pfmsoft.eve_argus.cli import app
from pfmsoft.eve_argus.cli.reports import hub_prices as command
from pfmsoft.eve_argus.dynamic import models, read, util, write
from pfmsoft.eve_argus.helpers.file_safe_string import file_safe_string
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS, MarketHub
from pfmsoft.eve_argus.reports.market_hub_prices import collect_market_hub_prices
from pfmsoft.eve_argus.reports.market_hub_prices_render import (
    render_market_hub_prices_csv,
    render_market_hub_prices_json,
)
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings
from pfmsoft.eve_argus.static import read as static_read
from pfmsoft.eve_argus.static.models import MarketGroupsDataset, TypesDataset
from pfmsoft.eve_argus.static.query_helpers import load_table_definitions
from pfmsoft.eve_argus.static.store import ManifestEntry, StaticManifest

RECEIVED = "2026-10-17T22:07:37.553890662Z"
GENERATED = Instant.parse_iso("2026-10-18T12:00:00Z")
NAME = 'Mineral, "special"\nvariant'


def summary(
    *, type_id: int = 34, buy: bool = True, hub: MarketHub = MARKET_HUBS[0]
) -> models.OrderSummaryRecord:
    """Build distinguishable exact metrics without recalculating prices."""
    return models.OrderSummaryRecord(
        region_id=hub.region_id,
        system_id=hub.system_id,
        location_id=None,
        type_id=type_id,
        is_buy_summary=buy,
        five_price=Decimal("123456789012345.67"),
        five_orders=2,
        five_items=11,
        lowest=Decimal("1.00"),
        highest=Decimal("1E+10"),
        total_items=100,
        total_orders=10,
        average=Decimal("12.34"),
        filtered_items=7,
        filtered_orders=3,
    )


def dataset(*, hub: MarketHub = MARKET_HUBS[0]) -> models.OrderSummaryDataset:
    """Include all four side-presence combinations and intentionally unsorted IDs."""
    return models.OrderSummaryDataset(
        response_metadata_id=17,
        received_at=RECEIVED,
        expires_at="2026-10-18T12:00:00Z",
        argus_expires_at=None,
        region_id=hub.region_id,
        system_id=hub.system_id,
        location_id=None,
        records={
            37: models.BuySellSummary(buy_summary=None, sell_summary=None),
            36: models.BuySellSummary(
                buy_summary=None, sell_summary=summary(type_id=36, buy=False, hub=hub)
            ),
            35: models.BuySellSummary(
                buy_summary=summary(type_id=35, hub=hub), sell_summary=None
            ),
            34: models.BuySellSummary(
                buy_summary=summary(hub=hub), sell_summary=summary(buy=False, hub=hub)
            ),
        },
    )


def response(data: models.OrderSummaryDataset) -> models.OrderSummaryResponse:
    """Keep summary and source IDs deliberately different."""
    return models.OrderSummaryResponse(
        order_summary_response_id=91,
        response_metadata_id=data.response_metadata_id,
        received_at=data.received_at,
        expires_at=data.expires_at,
        argus_expires_at=data.argus_expires_at,
        region_id=data.region_id,
        system_id=data.system_id,
        location_id=data.location_id,
    )


def populate_static(connection: sqlite3.Connection) -> None:
    """Use production tables/readers, including an unpublished and nonmarket type."""
    connection.executescript(load_table_definitions())
    connection.execute(
        """INSERT INTO market_groups
        (market_group_id, description, has_types, name, int_path, str_path, types)
        VALUES (10, '', 1, 'Minerals', '[10]', '["Minerals"]', '[34,35,37]')"""
    )
    connection.executemany(
        """INSERT INTO types
        (type_id, group_id, market_group_id, name, portion_size, published)
        VALUES (?, 1, ?, ?, 1, ?)""",
        [(34, 10, NAME, 1), (35, 10, "Unpublished", 0), (36, None, "No group", 1)],
    )
    connection.commit()


@pytest.fixture
def static_data() -> tuple[TypesDataset, MarketGroupsDataset]:
    """Load real static models instead of substituting untyped dictionaries."""
    with closing(sqlite3.connect(":memory:")) as connection:
        populate_static(connection)
        return (
            static_read.types(connection, only_published=False),
            static_read.market_groups(connection),
        )


def test_collection_and_formats(
    static_data: tuple[TypesDataset, MarketGroupsDataset],
) -> None:
    """Preserve every stored metric, omit neither-sided types and align both outputs."""
    types, groups = static_data
    data = dataset()
    report = collect_market_hub_prices(
        summaries=data,
        response=response(data),
        hub=MARKET_HUBS[0],
        types=types,
        market_groups=groups,
        generated_at=GENERATED,
    )
    assert [row.type_id for row in report.records] == [34, 35, 36]
    assert report.is_stale is True
    assert report.order_summary_response_id == 91
    assert report.response_metadata_id == 17
    assert report.scope == "system"
    parsed = json.loads(render_market_hub_prices_json(report))
    rows = list(csv.DictReader(StringIO(render_market_hub_prices_csv(report))))
    assert (
        [int(row["type_id"]) for row in rows]
        == [row["type_id"] for row in parsed["records"]]
        == [34, 35, 36]
    )
    assert parsed["schema_version"] == 1
    assert rows[0]["type_name"] == NAME
    assert parsed["records"][0]["market_path_ids"] == [10]
    assert parsed["records"][0]["market_path_names"] == ["Minerals"]
    assert rows[0]["market_path_ids"] == "10"
    assert rows[0]["market_path_names"] == "Minerals"
    assert parsed["records"][2]["market_group_id"] is None
    assert parsed["records"][2]["market_path_names"] is None
    assert rows[2]["market_path_names"] == ""
    for csv_row, json_row in zip(rows, parsed["records"], strict=True):
        for key, value in parsed.items():
            if key != "records":
                expected = "" if value is None else str(value)
                assert csv_row[key] == expected
        for side in ("buy", "sell"):
            metrics = json_row[f"{side}_summary"]
            assert csv_row[f"has_{side}_summary"] == str(metrics is not None)
            if metrics is None:
                assert csv_row[f"{side}_five_price"] == ""
                assert csv_row[f"{side}_total_orders"] == ""
            else:
                for key, value in metrics.items():
                    assert csv_row[f"{side}_{key}"] == str(value)
                assert metrics["five_price"] == "123456789012345.67"
                assert metrics["highest"] == "10000000000"
                assert isinstance(metrics["total_orders"], int)
    assert data == dataset()


@pytest.mark.parametrize(
    ("expiry", "argus_expiry", "stale"),
    [
        (None, None, None),
        ("2026-10-18T12:00:01Z", None, False),
        ("2026-10-18T12:00:00Z", None, True),
        ("2026-10-17T00:00:00Z", "2026-10-19T00:00:00Z", False),
        ("2026-10-19T00:00:00Z", "2026-10-17T00:00:00Z", True),
    ],
)
def test_empty_and_freshness(
    static_data: tuple[TypesDataset, MarketGroupsDataset],
    expiry: str | None,
    argus_expiry: str | None,
    stale: bool | None,
) -> None:
    """An empty latest snapshot keeps headers and JSON provenance, never older rows."""
    types, groups = static_data
    data = replace(
        dataset(), records={}, expires_at=expiry, argus_expires_at=argus_expiry
    )
    report = collect_market_hub_prices(
        summaries=data,
        response=response(data),
        hub=MARKET_HUBS[0],
        types=types,
        market_groups=groups,
        generated_at=GENERATED,
    )
    assert report.is_stale is stale
    reader = csv.DictReader(StringIO(render_market_hub_prices_csv(report)))
    assert list(reader) == []
    assert reader.fieldnames is not None and "sell_filtered_orders" in reader.fieldnames
    parsed = json.loads(render_market_hub_prices_json(report))
    assert parsed["records"] == []
    assert parsed["response_metadata_id"] == 17


@pytest.mark.parametrize(
    "change",
    [
        {"type_id": 99},
        {"region_id": 9},
        {"system_id": 9},
        {"location_id": 60003760},
        {"is_buy_summary": False},
    ],
)
def test_invalid_summary_rejected(
    static_data: tuple[TypesDataset, MarketGroupsDataset], change: dict[str, object]
) -> None:
    """Reject inconsistent row identity, scope or side instead of exporting it."""
    types, groups = static_data
    bad = replace(summary(), **change)
    data = replace(
        dataset(),
        records={34: models.BuySellSummary(buy_summary=bad, sell_summary=None)},
    )
    with pytest.raises(ValueError, match="summary"):
        collect_market_hub_prices(
            summaries=data,
            response=response(data),
            hub=MARKET_HUBS[0],
            types=types,
            market_groups=groups,
            generated_at=GENERATED,
        )


@pytest.mark.parametrize("failure", ["hub", "response", "type", "type_key", "group"])
def test_missing_static_and_metadata_mismatches(
    static_data: tuple[TypesDataset, MarketGroupsDataset],
    failure: Literal["hub", "response", "type", "type_key", "group"],
) -> None:
    """No mismatched provenance or missing required static names are silently accepted."""
    types, groups = static_data
    data = dataset()
    saved = response(data)
    hub = MARKET_HUBS[0]
    match failure:
        case "hub":
            hub = replace(hub, system_id=1)
        case "response":
            saved = replace(saved, response_metadata_id=1)
        case "type":
            types = {key: value for key, value in types.items() if key != 35}
        case "type_key":
            types = types | {34: replace(types[34], type_id=99)}
        case "group":
            groups = {}
    with pytest.raises(ValueError):
        collect_market_hub_prices(
            summaries=data,
            response=saved,
            hub=hub,
            types=types,
            market_groups=groups,
            generated_at=GENERATED,
        )


@dataclass(slots=True, kw_only=True)
class Environment:
    """On-disk local inputs exercised through the registered root CLI."""

    settings: EveArgusSettings
    dynamic_path: Path
    static_path: Path


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
        settings=settings, dynamic_path=dynamic_path, static_path=static_path
    )


def save(
    env: Environment,
    *,
    hub: MarketHub = MARKET_HUBS[0],
    received_at: str = RECEIVED,
    system: bool = True,
    station: bool = False,
    empty: bool = False,
) -> int:
    """Save summary scopes with deliberately distinct source and summary IDs."""
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
        connection.execute(
            """INSERT OR IGNORE INTO get_markets_region_id_orders_response
            (response_metadata_id, region_id, received_at) VALUES (?, ?, ?)""",
            (metadata_id, hub.region_id, received_at),
        )
        data = replace(
            dataset(hub=hub),
            response_metadata_id=metadata_id,
            received_at=received_at,
            expires_at="2026-10-18T00:00:00Z",
        )
        if empty or not system or station:
            data = replace(data, records={})
        data = replace(
            data,
            system_id=hub.system_id if system and not station else None,
            location_id=hub.station_id if station else None,
        )
        return write.order_summaries(connection, data)


def invoke(env: Environment, destination: Path, *args: str) -> Result:
    """Run actual registration, readers, collectors and renderers."""
    return CliRunner().invoke(
        app,
        ["reports", "hub-prices", "--to", str(destination), *args],
        obj={SETTINGS_KEY: env.settings},
    )


def save_all(env: Environment) -> None:
    """Give each hub a distinct source timestamp."""
    for index, hub in enumerate(MARKET_HUBS):
        save(env, hub=hub, received_at=f"2026-10-17T22:07:3{index}.553890662Z")


def test_cli_all_hubs_scope_selection_and_overwrite(
    environment: Environment,
    tmp_path: Path,
) -> None:
    """Select matching scopes before newest, preserving per-hub source timestamps."""
    save_all(environment)
    save(environment, received_at="2026-10-16T00:00:00Z", empty=True)
    save(environment, received_at="2026-10-19T00:00:00Z", system=False)
    save(environment, received_at="2026-10-20T00:00:00Z", station=True)
    destination = tmp_path / "reports"
    result = invoke(environment, destination, "--quiet")
    assert result.exit_code == 0, result.output
    assert "Warning" in result.output and "Wrote" not in result.output
    assert len(list(destination.iterdir())) == 10
    generations: set[str] = set()
    for index, hub in enumerate(MARKET_HUBS):
        timestamp = f"2026-10-17T22:07:3{index}.553890662Z"
        stem = f"price-summary-{hub.system_name}-{file_safe_string(timestamp)}"
        parsed = json.loads((destination / f"{stem}.json").read_text())
        assert parsed["received_at"] == timestamp
        assert parsed["system_id"] == hub.system_id
        assert parsed["region_name"] == hub.region_name
        assert len(parsed["records"]) == 3
        assert (destination / f"{stem}.csv").read_bytes()[:3] != b"\xef\xbb\xbf"
        generations.add(parsed["generated_at"])
    assert len(generations) == 1
    path = next(destination.glob("*.csv"))
    path.write_text("keep")
    result = invoke(environment, destination)
    assert result.exit_code == 1 and "--overwrite" in result.output
    assert path.read_text() == "keep"
    result = invoke(environment, destination, "--overwrite")
    assert result.exit_code == 0, result.output
    assert path.read_text() != "keep"


def test_cli_missing_hubs_no_output(environment: Environment, tmp_path: Path) -> None:
    """List all missing hubs, without implying a cached fetch always repairs them."""
    save(environment)
    destination = tmp_path / "reports"
    result = invoke(environment, destination, "--quiet")
    assert result.exit_code == 1
    assert all(hub.system_name in result.output for hub in MARKET_HUBS[1:])
    assert not destination.exists()


def test_cli_latest_empty_wins_and_scope_tie_breaker(
    environment: Environment,
    tmp_path: Path,
) -> None:
    """A newer empty system scope supersedes populated data despite later station IDs."""
    save_all(environment)
    saved_id = save(environment, received_at=RECEIVED, empty=True)
    save(environment, received_at=RECEIVED, station=True)
    destination = tmp_path / "reports"
    result = invoke(environment, destination)
    assert result.exit_code == 0, result.output
    path = destination / f"price-summary-Jita-{file_safe_string(RECEIVED)}.json"
    parsed = json.loads(path.read_text())
    assert parsed["records"] == []
    assert parsed["order_summary_response_id"] == saved_id


@pytest.mark.parametrize(
    "failure",
    ["destination", "static_type", "missing_manifest", "build", "collision", "name"],
)
def test_cli_preflight_errors_leave_no_exports(
    environment: Environment,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Literal[
        "destination", "static_type", "missing_manifest", "build", "collision", "name"
    ],
) -> None:
    """Validation failures do not leave success-shaped partial hub exports."""
    save_all(environment)
    destination = tmp_path / "reports"
    match failure:
        case "destination":
            destination.write_text("keep")
        case "static_type":
            with closing(sqlite3.connect(environment.static_path)) as connection:
                connection.execute("DELETE FROM types WHERE type_id = 35")
                connection.commit()
        case "missing_manifest":
            environment.settings.static_database_store = tmp_path / "missing"
        case "build":
            environment.settings.static_database_build_number = 999
        case "collision":
            hub = MARKET_HUBS[0]
            monkeypatch.setattr(command, "MARKET_HUBS", [hub, replace(hub)])
        case "name":
            monkeypatch.setattr(
                command, "MARKET_HUBS", [replace(MARKET_HUBS[0], system_name="!!!")]
            )
    result = invoke(environment, destination, "--quiet")
    assert result.exit_code == 1, result.output
    assert "Error" in result.output
    assert not destination.exists() or destination.is_file()


@pytest.mark.parametrize("field", ["received_at", "expires_at", "argus_expires_at"])
def test_invalid_timestamps(
    static_data: tuple[TypesDataset, MarketGroupsDataset],
    field: str,
) -> None:
    """Bad timestamps must not become successful exports with misleading freshness."""
    types, groups = static_data
    data = replace(dataset(), **{field: "invalid"})
    with pytest.raises(ValueError):
        collect_market_hub_prices(
            summaries=data,
            response=response(data),
            hub=MARKET_HUBS[0],
            types=types,
            market_groups=groups,
            generated_at=GENERATED,
        )


def test_multi_component_paths_and_csv_quoting(
    static_data: tuple[TypesDataset, MarketGroupsDataset],
) -> None:
    """Paths retain their ordered ID/name pairs, including quotes and newlines."""
    types, groups = static_data
    groups = groups | {
        10: replace(
            groups[10],
            int_path=(9, 10),
            str_path=('Root, "quoted"\nname', "Minerals"),
        )
    }
    data = dataset()
    report = collect_market_hub_prices(
        summaries=data,
        response=response(data),
        hub=MARKET_HUBS[0],
        types=types,
        market_groups=groups,
        generated_at=GENERATED,
    )
    row = next(csv.DictReader(StringIO(render_market_hub_prices_csv(report))))
    assert row["market_path_ids"] == "9/10"
    assert row["market_path_names"] == 'Root, "quoted"\nname/Minerals'
    assert json.loads(render_market_hub_prices_json(report))["records"][0][
        "market_path_ids"
    ] == [9, 10]


@pytest.mark.parametrize(
    "change",
    [
        {"market_group_id": 11},
        {"int_path": ()},
        {"str_path": ("Wrong",)},
        {"int_path": (9, 10)},
    ],
)
def test_invalid_static_paths(
    static_data: tuple[TypesDataset, MarketGroupsDataset],
    change: dict[str, object],
) -> None:
    """Reject mismatched market group keys, path tails or component counts."""
    types, groups = static_data
    groups = groups | {10: replace(groups[10], **change)}
    data = dataset()
    with pytest.raises(ValueError, match="static market"):
        collect_market_hub_prices(
            summaries=data,
            response=response(data),
            hub=MARKET_HUBS[0],
            types=types,
            market_groups=groups,
            generated_at=GENERATED,
        )


def test_read_only_inputs_and_missing_database(
    environment: Environment,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inputs are never writable, bootstrapped, or silently created when missing."""
    save_all(environment)
    original_manager = command.db_connection_manager

    def readonly_manager(
        path: str | Path,
        *,
        read_only: bool,
    ) -> AbstractContextManager[sqlite3.Connection]:
        """Assert that both production database contexts are opened read-only."""
        assert read_only
        return original_manager(path, read_only=read_only)

    manager = Mock(side_effect=readonly_manager)
    monkeypatch.setattr(command, "db_connection_manager", manager)
    before = environment.dynamic_path.read_bytes(), environment.static_path.read_bytes()
    result = invoke(environment, tmp_path / "reports")
    assert result.exit_code == 0, result.output
    assert manager.call_count == 2
    assert before == (
        environment.dynamic_path.read_bytes(),
        environment.static_path.read_bytes(),
    )
    environment.settings.argus_dynamic_database = tmp_path / "missing.sqlite"
    result = invoke(environment, tmp_path / "other")
    assert result.exit_code == 1 and "Error" in result.output
    assert not environment.settings.argus_dynamic_database.exists()


def test_empty_manifest_is_explicit_error(
    environment: Environment, tmp_path: Path
) -> None:
    """An empty store manifest stays untouched and produces no export."""
    manifest = tmp_path / "manifest.json"
    content = StaticManifest(entries={}).serialize()
    manifest.write_text(content)
    result = invoke(environment, tmp_path / "reports")
    assert result.exit_code == 1
    assert "No entry found for build number: None" in result.output
    assert manifest.read_text() == content


def test_filename_sanitization(
    environment: Environment, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hub names use the same sanitizer as fractional receipt timestamps."""
    save_all(environment)
    monkeypatch.setattr(
        command, "MARKET_HUBS", [replace(MARKET_HUBS[0], system_name="Ji/ta ?")]
    )
    result = invoke(environment, tmp_path / "reports")
    assert result.exit_code == 0, result.output
    assert {path.name for path in (tmp_path / "reports").iterdir()} == {
        f"price-summary-Ji_ta-2026-10-17T22_07_30_553890662Z.{suffix}"
        for suffix in ("csv", "json")
    }


def test_write_failure_is_not_success(
    environment: Environment, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A filesystem write error produces a nonzero exit and an explicit message."""
    save_all(environment)
    destination = tmp_path / "reports"
    original_open = Path.open

    def open_with_failure(
        self: Path,
        mode: Literal["r", "w", "x"] = "r",
        *,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> TextIOWrapper:
        """Fail only output opens, after all local input loading has succeeded."""
        if self.parent == destination:
            raise OSError("Synthetic write failure")
        return original_open(
            self, mode, encoding=encoding, errors=errors, newline=newline
        )

    monkeypatch.setattr(Path, "open", open_with_failure)
    result = invoke(environment, destination, "--quiet")
    assert result.exit_code == 1
    assert "Synthetic write failure" in result.output


def test_cli_fresh_snapshots_are_quiet(
    environment: Environment, tmp_path: Path
) -> None:
    """Quiet mode has no stale warning when the selected data remains valid."""
    save_all(environment)
    with closing(sqlite3.connect(environment.dynamic_path)) as connection:
        connection.execute(
            "UPDATE response_metadata SET expires_at = '2099-01-01T00:00:00Z'"
        )
        connection.commit()
    result = invoke(environment, tmp_path / "reports", "--quiet")
    assert result.exit_code == 0, result.output
    assert result.output == ""


def test_last_hub_collection_failure_writes_nothing(
    environment: Environment,
    tmp_path: Path,
) -> None:
    """Do not write earlier rendered hubs when enrichment of the last hub fails."""
    save_all(environment)
    hub = MARKET_HUBS[-1]
    saved_id = save(environment, hub=hub, received_at=RECEIVED)
    with closing(sqlite3.connect(environment.dynamic_path)) as connection:
        data = read.order_summaries(connection, saved_id)
        write.order_summaries(
            connection,
            replace(
                data,
                records={
                    999: models.BuySellSummary(
                        buy_summary=summary(type_id=999, hub=hub),
                        sell_summary=None,
                    )
                },
            ),
        )
    destination = tmp_path / "reports"
    result = invoke(environment, destination)
    assert result.exit_code == 1, result.output
    assert "static type 999" in result.output
    assert not destination.exists()
