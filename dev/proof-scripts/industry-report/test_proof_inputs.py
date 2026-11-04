"""Verify read-only adapters against synthetic SQLite databases, never live data."""

import hashlib
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from industry_proof import Source, build_report
from proof_inputs import DatabasePaths, history_market, read_inputs

PROJECT = Path(__file__).resolve().parents[3]
RECEIPT = "2020-01-11T00:00:00Z"


def create_database(path: Path, *, module: str) -> sqlite3.Connection:
    """Create only a temporary fixture using the project's existing SQL schema."""
    connection = sqlite3.connect(path)
    schema = PROJECT / "src/pfmsoft/eve_argus" / module / "table_definitions.sql"
    connection.executescript(schema.read_text(encoding="utf-8"))
    return connection


def insert_history(connection: sqlite3.Connection, *, day: int, volume: int) -> None:
    """Insert a fixed-price regional history fixture in stored cents."""
    connection.execute(
        "INSERT INTO market_history "
        "(received_at, region_id, type_id, average, date_, highest, lowest, "
        "order_count, volume) VALUES (?, 10000002, 100, 200, ?, 200, 200, 1, ?)",
        (RECEIPT, f"2020-01-{day:02d}", volume),
    )


def test_history_window_coverage_zero_and_receipts(tmp_path: Path) -> None:
    """Anchor on available dates, divide by ten, and preserve every used receipt."""
    connection = create_database(tmp_path / "history.sqlite", module="market_history")
    try:
        for day in range(1, 11):
            insert_history(connection, day=day, volume=day * 10)
        insert_history(connection, day=12, volume=9999)
        sources: list[Source] = []
        market = history_market(
            connection,
            region_id=10000002,
            station_id=60003760,
            type_id=100,
            sources=sources,
            before="2020-01-12",
        )
        assert market.history_end == "2020-01-10"
        assert market.history_start == "2020-01-01"
        assert market.daily_sales == 55
        assert market.history_price == 2
        assert market.days_present == 10
        assert sources[0].received_at == RECEIPT
        connection.execute("DELETE FROM market_history WHERE date_ = '2020-01-02'")
        market = history_market(
            connection,
            region_id=10000002,
            station_id=60003760,
            type_id=100,
            sources=[],
            before="2020-01-12",
        )
        assert market.daily_sales == 53
        assert market.days_present == 9
        connection.execute("UPDATE market_history SET volume = 0")
        market = history_market(
            connection,
            region_id=10000002,
            station_id=60003760,
            type_id=100,
            sources=[],
            before="2020-01-12",
        )
        assert market.daily_sales == 0
        assert market.history_price is None
        absent = history_market(
            connection,
            region_id=10000002,
            station_id=60003760,
            type_id=999,
            sources=[],
            before="2020-01-12",
        )
        assert absent.daily_sales is None
    finally:
        connection.close()


@pytest.fixture
def snapshot_paths(tmp_path: Path) -> DatabasePaths:
    """Seed old/new and differently scoped snapshots with deliberately different prices."""
    paths = DatabasePaths(
        static=tmp_path / "static.sqlite",
        dynamic=tmp_path / "dynamic.sqlite",
        history=tmp_path / "history.sqlite",
    )
    static = create_database(paths.static, module="static")
    dynamic = create_database(paths.dynamic, module="dynamic")
    history = create_database(paths.history, module="market_history")
    try:
        static.executescript("""
            INSERT INTO categories(category_id, published) VALUES (7, 1);
            INSERT INTO groups(group_id, anchorable, anchored, category_id,
                fittable_non_singleton, name, published, use_base_price)
                VALUES (1, 0, 0, 7, 0, 'Fixture group', 1, 0);
            INSERT INTO types(type_id, group_id, name, portion_size, published)
                VALUES (1, 1, 'Fixture material', 1, 1),
                       (100, 1, 'Fixture product', 1, 1),
                       (1100, 1, 'Fixture blueprint', 1, 1);
            INSERT INTO blueprints VALUES (1100, 100);
            INSERT INTO blueprint_activities VALUES
                (1100, 'manufacturing', 600), (1100, 'copying', 60);
            INSERT INTO blueprint_activity_products
                (blueprint_type_id, activity, product_type_id, quantity)
                VALUES (1100, 'manufacturing', 100, 1);
            INSERT INTO blueprint_activity_materials
                VALUES (1100, 'manufacturing', 1, 2);
            INSERT INTO map_regions(region_id, name, nebula_id, position_x, position_y, position_z)
                VALUES (1, 'Fixture region', 1, 0, 0, 0);
            INSERT INTO map_constellations
                (constellation_id, name, position_x, position_y, position_z, region_id)
                VALUES (1, 'Fixture constellation', 0, 0, 0, 1);
            INSERT INTO map_solar_systems(solar_system_id, constellation_id, name,
                luminosity, position_x, position_y, position_z, radius, region_id, security_status)
                VALUES (999, 1, 'Osmeden', 1, 0, 0, 0, 1, 1, 0.7);
            INSERT INTO sde_metadata VALUES (1, '2020-01-01');
        """)
        for i in range(1, 9):
            dynamic.execute(
                "INSERT INTO response_metadata(id, received_at) VALUES (?, ?)",
                (i, f"2020-01-{i:02d}T00:00:00Z"),
            )
        dynamic.executescript("""
            INSERT INTO get_markets_prices_response(response_metadata_id) VALUES (1), (2);
            INSERT INTO markets_prices(type_id, adjusted_price, response_metadata_id)
                VALUES (1, 99900, 1), (1, 200, 2);
            INSERT INTO get_industry_systems_response(response_metadata_id) VALUES (3);
            INSERT INTO system_cost_indices(system_id, copying, manufacturing, invention,
                response_metadata_id) VALUES (999, 400, 300, 200, 3);
            INSERT INTO get_corporations_corporation_id_blueprints_response
                (response_metadata_id, corporation_id) VALUES (4, 7), (5, 8);
            INSERT INTO corporation_blueprints(corporation_id, item_id, type_id, location_id,
                location_flag, quantity, time_efficiency, material_efficiency, runs,
                response_metadata_id)
                VALUES (7, 1000, 1100, 1, 'Hangar', -1, 20, 10, -1, 4),
                       (8, 2000, 1100, 1, 'Hangar', -1, 0, 0, -1, 5);
            INSERT INTO get_markets_region_id_orders_response
                (response_metadata_id, region_id, received_at)
                VALUES (6, 10000002, '2020-01-06T00:00:00Z'),
                       (7, 10000002, '2020-01-07T00:00:00Z'),
                       (8, 10000043, '2020-01-08T00:00:00Z');
        """)
        # Latest Jita book: lowest sell 3, 5% boundary 4; another station offers 1.
        for order, response, station, type_id, cents, volume in (
            (1, 6, 60003760, 1, 99900, 100),
            (2, 7, 60003760, 1, 300, 2),
            (3, 7, 60003760, 1, 400, 98),
            (4, 7, 9999, 1, 100, 100),
            (5, 7, 60003760, 100, 100000, 100),
            (6, 8, 60008494, 1, 77700, 100),
        ):
            dynamic.execute(
                "INSERT INTO market_orders(response_metadata_id, region_id, duration, "
                "is_buy_order, issued, location_id, min_volume, order_id, price, range_, "
                "system_id, type_id, volume_remain, volume_total) "
                "VALUES (?, ?, 90, 0, ?, ?, 1, ?, ?, 'station', 1, ?, ?, ?)",
                (
                    response,
                    10000043 if response == 8 else 10000002,
                    RECEIPT,
                    station,
                    order,
                    cents,
                    type_id,
                    volume,
                    volume,
                ),
            )
        for day in range(1, 11):
            insert_history(history, day=day, volume=10)
        for connection in (static, dynamic, history):
            connection.commit()
    finally:
        for connection in (static, dynamic, history):
            connection.close()
    return paths


def test_read_only_snapshot_linkage(snapshot_paths: DatabasePaths) -> None:
    """Use latest scoped responses and Jita sell 5%, without modifying databases."""
    paths = (snapshot_paths.static, snapshot_paths.dynamic, snapshot_paths.history)
    before = [hashlib.sha256(path.read_bytes()).digest() for path in paths]
    data, selected = read_inputs(snapshot_paths, corporation_id=7, product_ids=(100,))
    assert selected == (100,)
    assert data.originals[0].item_id == 1000
    assert data.adjusted_prices[1] == 2
    assert data.input_prices[1] == 4
    assert data.indices["manufacturing"] == Decimal("0.03")
    assert data.markets[60003760, 100].daily_sales == 10
    assert any(
        s.label == "Jita station orders" and s.reference == "7" for s in data.sources
    )
    report = build_report(data, product_ids=selected)
    assert all(plan.status == "complete" for plan in report.plans)
    assert [hashlib.sha256(path.read_bytes()).digest() for path in paths] == before
    with pytest.raises(ValueError, match="corporation BPO inventory"):
        read_inputs(snapshot_paths, corporation_id=9)


def test_loads_prices_for_copy_only_consumables(snapshot_paths: DatabasePaths) -> None:
    """Fetch stored Jita prices even when inputs appear only in copying."""
    with sqlite3.connect(snapshot_paths.static) as connection:
        connection.executescript("""
            INSERT INTO types(type_id, group_id, name, portion_size, published)
                VALUES (3812, 1, 'Data Sheets', 1, 1);
            INSERT INTO blueprint_activity_materials
                VALUES (1100, 'copying', 3812, 20);
        """)
    with sqlite3.connect(snapshot_paths.dynamic) as connection:
        connection.execute(
            """
            INSERT INTO market_orders
            (response_metadata_id, region_id, duration, is_buy_order, issued,
             location_id, min_volume, order_id, price, range_, system_id,
             type_id, volume_remain, volume_total)
            VALUES (7, 10000002, 90, 0, ?, 60003760, 1, 999, 24390,
                    'station', 30000142, 3812, 10000, 10000)
        """,
            (RECEIPT,),
        )
    data, selected = read_inputs(snapshot_paths, corporation_id=7, product_ids=(100,))
    assert data.input_prices[3812] == Decimal("243.90")
    report = build_report(data, product_ids=selected)
    assert all(plan.status == "complete" for plan in report.plans)
    assert all(
        next(p for p in plan.shopping if p.type_id == 3812).quantity == 200
        for plan in report.plans
    )


def test_reads_product_market_path(snapshot_paths: DatabasePaths) -> None:
    """Carry the full stored market-group path into presentation inputs."""
    with sqlite3.connect(snapshot_paths.static) as connection:
        connection.executescript("""
            INSERT INTO market_groups
                (market_group_id, has_types, name, int_path, str_path)
                VALUES (42, 1, 'Modules', '[1, 42]', '["Ship Equipment", "Modules"]');
            UPDATE types SET market_group_id = 42 WHERE type_id = 100;
        """)
    data, _ = read_inputs(snapshot_paths, corporation_id=7, product_ids=(100,))
    assert data.items[100].market_path == "Ship Equipment/Modules"
    assert data.items[1].market_path is None


def test_missing_database_does_not_create_files(tmp_path: Path) -> None:
    """An invalid read-only path never initializes a new application database."""
    absent = tmp_path / "absent.sqlite"
    with pytest.raises(ValueError, match="does not exist"):
        read_inputs(
            DatabasePaths(static=absent, dynamic=absent, history=absent),
            corporation_id=7,
        )
    assert not absent.exists()


def test_copy_consumables_are_loaded_and_costed(
    snapshot_paths: DatabasePaths,
) -> None:
    """Load copying recipes and charge their materials per licensed run."""
    with sqlite3.connect(snapshot_paths.static) as connection:
        connection.executescript("""
            INSERT INTO types(type_id, group_id, name, portion_size, published)
                VALUES (101, 1, 'Other product', 1, 1),
                       (1101, 1, 'Other blueprint', 1, 1);
            INSERT INTO blueprints VALUES (1101, 100);
            INSERT INTO blueprint_activities VALUES
                (1101, 'manufacturing', 600), (1101, 'copying', 60);
            INSERT INTO blueprint_activity_products
                (blueprint_type_id, activity, product_type_id, quantity)
                VALUES (1101, 'manufacturing', 101, 1);
            INSERT INTO blueprint_activity_materials
                VALUES (1101, 'copying', 1, 1);
        """)
    data, selected = read_inputs(snapshot_paths, corporation_id=7, product_ids=(100,))
    assert all(
        plan.status == "complete"
        for plan in build_report(data, product_ids=selected).plans
    )
    with sqlite3.connect(snapshot_paths.static) as connection:
        connection.execute(
            "INSERT INTO blueprint_activity_materials VALUES (1100, 'copying', 1, 1)"
        )
    data, selected = read_inputs(snapshot_paths, corporation_id=7, product_ids=(100,))
    for plan in build_report(data, product_ids=selected).plans:
        assert plan.status == "complete"
        copies = [job for job in plan.jobs if job.activity == "copying"]
        assert sum(m.quantity for job in copies for m in job.inputs) == 10
        assert plan.nodes[0].cost == plan.total


def test_unpublished_skill_references(snapshot_paths: DatabasePaths) -> None:
    """Keep recipe skill identities even when static types are unpublished."""
    with sqlite3.connect(snapshot_paths.static) as connection:
        connection.executescript("""
            INSERT INTO types(type_id, group_id, name, portion_size, published)
                VALUES (3365, 1, 'Unpublished required skill', 1, 0);
            INSERT INTO blueprint_activity_skills VALUES
                (1100, 'manufacturing', 3365, 1);
        """)
    data, selected = read_inputs(snapshot_paths, corporation_id=7, product_ids=(100,))
    assert all(
        plan.status == "complete"
        for plan in build_report(data, product_ids=selected).plans
    )
