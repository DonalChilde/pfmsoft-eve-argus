"""Verify industry input selection against synthetic stored snapshots."""

import hashlib
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from pfmsoft.eve_argus.cli import app
from pfmsoft.eve_argus.cli.reports import industry as command
from pfmsoft.eve_argus.cli.reports._industry_inputs import DatabasePaths, read_inputs
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 1, 12, tzinfo=UTC)


@pytest.fixture
def paths(tmp_path: Path) -> DatabasePaths:
    """Create independent static, dynamic and history snapshots."""
    paths = DatabasePaths(
        static=tmp_path / "static.sqlite",
        dynamic=tmp_path / "dynamic.sqlite",
        history=tmp_path / "history.sqlite",
    )
    for path, module in (
        (paths.static, "static"),
        (paths.dynamic, "dynamic"),
        (paths.history, "market_history"),
    ):
        with sqlite3.connect(path) as connection:
            schema = ROOT / "src/pfmsoft/eve_argus" / module / "table_definitions.sql"
            connection.executescript(schema.read_text(encoding="utf-8"))
    with sqlite3.connect(paths.static) as db:
        db.executescript("""
            INSERT INTO categories(category_id, published) VALUES (7, 1);
            INSERT INTO groups(group_id, anchorable, anchored, category_id,
                fittable_non_singleton, name, published, use_base_price)
                VALUES (1, 0, 0, 7, 0, 'Fixture group', 1, 0);
            INSERT INTO types(type_id, group_id, name, portion_size, published)
                VALUES (1, 1, 'Material', 1, 1),
                       (100, 1, 'Product', 1, 1),
                       (1100, 1, 'Blueprint', 1, 1);
            INSERT INTO blueprints VALUES (1100, 100);
            INSERT INTO blueprint_activities VALUES
                (1100, 'manufacturing', 600), (1100, 'copying', 60);
            INSERT INTO blueprint_activity_products
                (blueprint_type_id, activity, product_type_id, quantity)
                VALUES (1100, 'manufacturing', 100, 1);
            INSERT INTO blueprint_activity_materials
                VALUES (1100, 'manufacturing', 1, 2);
            INSERT INTO map_regions(region_id, name, nebula_id, position_x, position_y, position_z)
                VALUES (1, 'Region', 1, 0, 0, 0);
            INSERT INTO map_constellations
                (constellation_id, name, position_x, position_y, position_z, region_id)
                VALUES (1, 'Constellation', 0, 0, 0, 1);
            INSERT INTO map_solar_systems(solar_system_id, constellation_id, name,
                luminosity, position_x, position_y, position_z, radius, region_id, security_status)
                VALUES (999, 1, 'Low security', 1, 0, 0, 0, 1, 1, 0.1),
                       (998, 1, 'Other', 1, 0, 0, 0, 1, 1, 0.8);
            INSERT INTO sde_metadata VALUES (1, '2026-01-01');
        """)
    with sqlite3.connect(paths.dynamic) as db:
        for i in range(1, 8):
            db.execute(
                "INSERT INTO response_metadata(id, received_at) VALUES (?, ?)",
                (i, f"2026-01-{i:02}T00:00:00Z"),
            )
        db.executescript("""
            INSERT INTO get_markets_prices_response(response_metadata_id) VALUES (1), (2);
            INSERT INTO markets_prices(type_id, adjusted_price, response_metadata_id)
                VALUES (1, 99900, 1), (1, 200, 2);
            INSERT INTO get_industry_systems_response(response_metadata_id) VALUES (3);
            INSERT INTO system_cost_indices(system_id, copying, manufacturing, invention,
                response_metadata_id) VALUES (999, 400, 300, 200, 3),
                                             (998, 500, 900, 600, 3);
            INSERT INTO get_corporations_corporation_id_blueprints_response
                (response_metadata_id, corporation_id) VALUES (4, 7), (5, 8);
            INSERT INTO corporation_blueprints(corporation_id, item_id, type_id, location_id,
                location_flag, quantity, time_efficiency, material_efficiency, runs,
                response_metadata_id)
                VALUES (7, 1000, 1100, 1, 'Hangar', -1, 20, 10, -1, 4),
                       (8, 2000, 1100, 1, 'Hangar', -1, 0, 0, -1, 5);
            INSERT INTO get_markets_region_id_orders_response
                (response_metadata_id, region_id, received_at)
                VALUES (6, 10000002, '2026-01-06T00:00:00Z'),
                       (7, 10000002, '2026-01-07T00:00:00Z');
        """)
        for order, response, price, volume in (
            (1, 6, 99900, 100),
            (2, 7, 300, 2),
            (3, 7, 400, 98),
        ):
            db.execute(
                "INSERT INTO market_orders(response_metadata_id, region_id, duration, "
                "is_buy_order, issued, location_id, min_volume, order_id, price, range_, "
                "system_id, type_id, volume_remain, volume_total) "
                "VALUES (?, 10000002, 90, 0, '2026-01-07T00:00:00Z', "
                "60003760, 1, ?, ?, 'station', 30000142, 1, ?, ?)",
                (response, order, price, volume, volume),
            )
    with sqlite3.connect(paths.history) as db:
        for day in range(1, 11):
            db.execute(
                "INSERT INTO market_history(received_at, region_id, type_id, average, "
                "date_, highest, lowest, order_count, volume) "
                "VALUES ('2026-01-11T00:00:00Z', 10000002, 100, 200, ?, 200, 200, 1, 10)",
                (f"2026-01-{day:02}",),
            )
    return paths


def test_snapshot_scopes_and_selected_system(paths: DatabasePaths) -> None:
    """Use latest response IDs and the requested system, without modifying sources."""
    files = (paths.static, paths.dynamic, paths.history)
    before = [hashlib.sha256(path.read_bytes()).digest() for path in files]
    data, selected = read_inputs(
        paths, corporation_id=7, system_id=999, generated_at=NOW, product_ids=(100,)
    )
    assert selected == (100,)
    assert data.system_name == "Low security"
    assert data.indices["manufacturing"] == Decimal("0.03")
    assert data.originals[0].item_id == 1000
    assert data.adjusted_prices[1] == 2
    assert data.input_prices[1] == 4
    assert data.markets[60003760, 100].daily_sales == 10
    assert any(
        s.label == "Jita station orders" and s.reference == "7" for s in data.sources
    )
    other, _ = read_inputs(
        paths, corporation_id=7, system_id=998, generated_at=NOW, product_ids=(100,)
    )
    assert other.indices["manufacturing"] == Decimal("0.09")
    assert [hashlib.sha256(path.read_bytes()).digest() for path in files] == before


def test_invalid_system_and_missing_history(
    paths: DatabasePaths, tmp_path: Path
) -> None:
    """Unknown systems fail; missing history leaves outcomes unavailable with a hint."""
    with pytest.raises(ValueError, match="Unknown solar system"):
        read_inputs(paths, corporation_id=7, system_id=1, generated_at=NOW)
    no_history = DatabasePaths(
        static=paths.static, dynamic=paths.dynamic, history=tmp_path / "absent"
    )
    data, _ = read_inputs(
        no_history,
        corporation_id=7,
        system_id=999,
        generated_at=NOW,
        product_ids=(100,),
    )
    assert data.markets[60003760, 100].history_price is None
    assert any("fetch market-history" in warning for warning in data.warnings)


def test_missing_skill_reference_is_actionable(paths: DatabasePaths) -> None:
    """Broken static skill references do not escape as unhandled key errors."""
    with sqlite3.connect(paths.static) as db:
        db.execute(
            "INSERT INTO blueprint_activity_skills VALUES (1100, 'manufacturing', 9999, 1)"
        )
    with pytest.raises(ValueError, match="9999"):
        read_inputs(paths, corporation_id=7, system_id=999, generated_at=NOW)


def test_real_cli_with_synthetic_snapshots(
    paths: DatabasePaths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run collection, planning and packaged renderers against real fixture databases."""
    settings = Mock(spec=EveArgusSettings)
    settings.corporation_id = 7
    settings.argus_dynamic_database = paths.dynamic
    settings.market_history_database = paths.history
    monkeypatch.setattr(command, "get_static_database_path", lambda _: paths.static)
    result = CliRunner().invoke(
        app,
        [
            "reports",
            "industry",
            "--to",
            str(tmp_path / "out"),
            "--system-id",
            "999",
            "--type-id",
            "100",
            "--quiet",
        ],
        obj={SETTINGS_KEY: settings},
    )
    assert result.exit_code == 0, (result.output, result.exception)
    assert "stale" in result.output
    directory = next((tmp_path / "out").iterdir())
    assert (directory / "industry-report.csv").is_file()
    assert (directory / "markdown" / "group-1.md").is_file()
    assumptions = (directory / "html" / "assumptions.html").read_text(encoding="utf-8")
    assert "Low security (999)" in assumptions
    assert "3.60%" in assumptions
