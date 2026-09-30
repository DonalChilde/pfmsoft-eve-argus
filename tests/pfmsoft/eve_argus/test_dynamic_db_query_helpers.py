"""Tests for dynamic database query helpers."""

import sqlite3
from decimal import Decimal

from pfmsoft.eve_argus.dynamic.db import load_table_definitions, query_helpers
from pfmsoft.eve_argus.dynamic.db.models import (
    BuySellOrders,
    CorporationBlueprintRecord,
    CorporationBlueprintsDataset,
    CorporationBlueprintsResponse,
    CorporationIndustryJobRow,
    CorporationIndustryJobsDataset,
    CorporationIndustryJobsResponse,
    MarketOrderRecord,
    MarketOrdersDataset,
    MarketOrdersResponse,
    MarketsPriceRecord,
    MarketsPricesDataset,
    MarketsPricesResponse,
    ResponseMetadata,
    SystemCostIndexRecord,
    SystemCostIndicesDataset,
    SystemCostIndicesResponse,
)


def _make_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(load_table_definitions())
    return connection


def test_get_response_metadata_filters_by_ids() -> None:
    """Metadata lookup returns all, selected, or no rows as requested."""
    connection = _make_connection()
    connection.executemany(
        """
        INSERT INTO response_metadata (
            received_at, expires_at, argus_expires_at
        ) VALUES (?, ?, ?)
        """,
        [
            ("2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z", None),
            ("2026-09-03T00:00:00Z", None, "2026-09-04T00:00:00Z"),
        ],
    )

    expected = [
        ResponseMetadata(
            response_metadata_id=1,
            received_at="2026-09-01T00:00:00Z",
            expires_at="2026-09-02T00:00:00Z",
            argus_expires_at=None,
        ),
        ResponseMetadata(
            response_metadata_id=2,
            received_at="2026-09-03T00:00:00Z",
            expires_at=None,
            argus_expires_at="2026-09-04T00:00:00Z",
        ),
    ]

    assert query_helpers.get_response_metadata(connection, None) == expected
    assert query_helpers.get_response_metadata(connection, {2}) == [expected[1]]
    assert query_helpers.get_response_metadata(connection, set()) == []


def test_get_markets_prices_responses_returns_linked_metadata() -> None:
    """Only metadata linked to universe prices responses is returned."""
    connection = _make_connection()
    connection.executemany(
        """
        INSERT INTO response_metadata (received_at, expires_at, argus_expires_at)
        VALUES (?, ?, ?)
        """,
        [
            ("2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z", None),
            ("2026-09-03T00:00:00Z", None, "2026-09-04T00:00:00Z"),
        ],
    )
    connection.execute(
        """
        INSERT INTO get_markets_prices_response (response_metadata_id)
        VALUES (?)
        """,
        (1,),
    )

    assert query_helpers.get_markets_prices_responses(connection) == [
        MarketsPricesResponse(
            response_metadata_id=1,
            received_at="2026-09-01T00:00:00Z",
            expires_at="2026-09-02T00:00:00Z",
            argus_expires_at=None,
        )
    ]


def test_get_markets_prices_returns_dataset_and_converts_prices() -> None:
    """Universe prices lookup returns metadata and prices as Decimal values."""
    connection = _make_connection()
    connection.execute(
        """
        INSERT INTO response_metadata (received_at, expires_at, argus_expires_at)
        VALUES (?, ?, ?)
        """,
        ("2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z", None),
    )
    connection.execute(
        """
        INSERT INTO get_markets_prices_response (response_metadata_id)
        VALUES (?)
        """,
        (1,),
    )
    connection.executemany(
        """
        INSERT INTO markets_prices (
            type_id, average_price, adjusted_price, response_metadata_id
        ) VALUES (?, ?, ?, ?)
        """,
        [(34, 12345, 10000, 1), (35, None, 250, 1)],
    )

    assert query_helpers.get_markets_prices(connection, 1) == MarketsPricesDataset(
        response_metadata_id=1,
        received_at="2026-09-01T00:00:00Z",
        expires_at="2026-09-02T00:00:00Z",
        argus_expires_at=None,
        records={
            34: MarketsPriceRecord(
                type_id=34,
                average_price=Decimal("123.45"),
                adjusted_price=Decimal("100.00"),
                response_metadata_id=1,
            ),
            35: MarketsPriceRecord(
                type_id=35,
                average_price=None,
                adjusted_price=Decimal("2.50"),
                response_metadata_id=1,
            ),
        },
    )


def test_get_market_orders_returns_grouped_buy_and_sell_order_records() -> None:
    """Market orders lookup reconstructs metadata and type-grouped buy/sell orders."""
    connection = _make_connection()
    connection.executemany(
        """
        INSERT INTO response_metadata (received_at, expires_at, argus_expires_at)
        VALUES (?, ?, ?)
        """,
        [
            ("2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z", None),
            ("2026-09-03T00:00:00Z", None, "2026-09-04T00:00:00Z"),
        ],
    )
    connection.executemany(
        """
        INSERT INTO get_markets_region_id_orders_response (
            response_metadata_id, region_id
        ) VALUES (?, ?)
        """,
        [(1, 10000002), (2, 10000005)],
    )
    connection.executemany(
        """
        INSERT INTO market_orders (
            response_metadata_id, region_id, duration, is_buy_order, issued,
            location_id, min_volume, order_id, price, range_, system_id,
            type_id, volume_remain, volume_total
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                1,
                10000002,
                90,
                1,
                "2026-09-01T00:00:00Z",
                60003760,
                1,
                101,
                15000,
                "station",
                30000142,
                34,
                10,
                10,
            ),
            (
                1,
                10000002,
                90,
                0,
                "2026-09-01T00:00:01Z",
                60003760,
                1,
                102,
                16000,
                "station",
                30000142,
                34,
                5,
                5,
            ),
            (
                2,
                10000005,
                90,
                1,
                "2026-09-03T00:00:00Z",
                60003760,
                1,
                201,
                1000,
                "station",
                30000142,
                35,
                1,
                1,
            ),
        ],
    )

    assert query_helpers.get_market_orders_responses(connection, None) == [
        MarketOrdersResponse(
            response_metadata_id=1,
            received_at="2026-09-01T00:00:00Z",
            expires_at="2026-09-02T00:00:00Z",
            argus_expires_at=None,
            region_id=10000002,
        ),
        MarketOrdersResponse(
            response_metadata_id=2,
            received_at="2026-09-03T00:00:00Z",
            expires_at=None,
            argus_expires_at="2026-09-04T00:00:00Z",
            region_id=10000005,
        ),
    ]
    assert query_helpers.get_market_orders(connection, 1) == MarketOrdersDataset(
        response_metadata_id=1,
        received_at="2026-09-01T00:00:00Z",
        expires_at="2026-09-02T00:00:00Z",
        argus_expires_at=None,
        region_id=10000002,
        records={
            34: BuySellOrders(
                buy_orders=(
                    MarketOrderRecord(
                        response_metadata_id=1,
                        region_id=10000002,
                        duration=90,
                        is_buy_order=True,
                        issued="2026-09-01T00:00:00Z",
                        location_id=60003760,
                        min_volume=1,
                        order_id=101,
                        price=Decimal("150.00"),
                        range="station",
                        system_id=30000142,
                        type_id=34,
                        volume_remain=10,
                        volume_total=10,
                    ),
                ),
                sell_orders=(
                    MarketOrderRecord(
                        response_metadata_id=1,
                        region_id=10000002,
                        duration=90,
                        is_buy_order=False,
                        issued="2026-09-01T00:00:01Z",
                        location_id=60003760,
                        min_volume=1,
                        order_id=102,
                        price=Decimal("160.00"),
                        range="station",
                        system_id=30000142,
                        type_id=34,
                        volume_remain=5,
                        volume_total=5,
                    ),
                ),
            )
        },
    )


def test_get_system_cost_indices_returns_dataset_and_converts_values() -> None:
    """System cost index lookup reconstructs metadata and four-place decimals."""
    connection = _make_connection()
    connection.execute(
        """
        INSERT INTO response_metadata (received_at, expires_at, argus_expires_at)
        VALUES (?, ?, ?)
        """,
        ("2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z", None),
    )
    connection.execute(
        """
        INSERT INTO get_industry_systems_response (response_metadata_id)
        VALUES (?)
        """,
        (1,),
    )
    connection.executemany(
        """
        INSERT INTO system_cost_indices (
            system_id, copying, manufacturing, invention, reaction,
            researching_material_efficiency, researching_time_efficiency,
            response_metadata_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (30000142, 10000, 12345, None, 20000, 30000, 40000, 1),
            (30000143, None, 5555, 6666, None, None, 7777, 1),
        ],
    )

    assert query_helpers.get_system_cost_indices_responses(connection) == [
        SystemCostIndicesResponse(
            response_metadata_id=1,
            received_at="2026-09-01T00:00:00Z",
            expires_at="2026-09-02T00:00:00Z",
            argus_expires_at=None,
        )
    ]
    assert query_helpers.get_system_cost_indices(
        connection, 1
    ) == SystemCostIndicesDataset(
        response_metadata_id=1,
        received_at="2026-09-01T00:00:00Z",
        expires_at="2026-09-02T00:00:00Z",
        argus_expires_at=None,
        records={
            30000142: SystemCostIndexRecord(
                system_id=30000142,
                copying=Decimal("1.0000"),
                manufacturing=Decimal("1.2345"),
                invention=None,
                reaction=Decimal("2.0000"),
                researching_material_efficiency=Decimal("3.0000"),
                researching_time_efficiency=Decimal("4.0000"),
                response_metadata_id=1,
            ),
            30000143: SystemCostIndexRecord(
                system_id=30000143,
                copying=None,
                manufacturing=Decimal("0.5555"),
                invention=Decimal("0.6666"),
                reaction=None,
                researching_material_efficiency=None,
                researching_time_efficiency=Decimal("0.7777"),
                response_metadata_id=1,
            ),
        },
    )


def test_get_corporation_industry_jobs_returns_dataset_and_converts_cost() -> None:
    """Industry jobs lookup reconstructs metadata and job records."""
    connection = _make_connection()
    connection.executemany(
        """
        INSERT INTO response_metadata (received_at, expires_at, argus_expires_at)
        VALUES (?, ?, ?)
        """,
        [
            ("2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z", None),
            ("2026-09-03T00:00:00Z", None, "2026-09-04T00:00:00Z"),
        ],
    )
    connection.executemany(
        """
        INSERT INTO get_corporations_corporation_id_industry_jobs_response (
            response_metadata_id, corporation_id
        ) VALUES (?, ?)
        """,
        [(1, 98000001), (2, 98000002)],
    )
    connection.executemany(
        """
        INSERT INTO corporation_industry_jobs (
            corporation_id, activity_id, blueprint_id, blueprint_location_id,
            blueprint_type_id, completed_character_id, completed_date, cost,
            duration, end_date, facility_id, installer_id, job_id, licensed_runs,
            location_id, output_location_id, pause_date, probability, product_type_id,
            runs, start_date, status, successful_runs, response_metadata_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                98000001,
                1,
                1001,
                60003760,
                34,
                42,
                "2026-09-01T00:00:00Z",
                12345,
                90,
                "2026-09-02T00:00:00Z",
                60000001,
                43,
                5001,
                1,
                60003760,
                60003800,
                "2026-09-01T00:00:01Z",
                0.5,
                35,
                1,
                "2026-09-01T00:00:00Z",
                "active",
                0,
                1,
            ),
            (
                98000002,
                3,
                2001,
                60003761,
                36,
                None,
                None,
                None,
                60,
                "2026-09-03T00:00:00Z",
                60000002,
                44,
                5002,
                None,
                60003761,
                60003801,
                None,
                None,
                None,
                10,
                "2026-09-03T00:00:00Z",
                "delivered",
                1,
                2,
            ),
        ],
    )

    assert query_helpers.get_corporation_industry_jobs_responses(connection, None) == [
        CorporationIndustryJobsResponse(
            response_metadata_id=1,
            received_at="2026-09-01T00:00:00Z",
            expires_at="2026-09-02T00:00:00Z",
            argus_expires_at=None,
            corporation_id=98000001,
        ),
        CorporationIndustryJobsResponse(
            response_metadata_id=2,
            received_at="2026-09-03T00:00:00Z",
            expires_at=None,
            argus_expires_at="2026-09-04T00:00:00Z",
            corporation_id=98000002,
        ),
    ]
    assert query_helpers.get_corporation_industry_jobs(
        connection, 1
    ) == CorporationIndustryJobsDataset(
        response_metadata_id=1,
        received_at="2026-09-01T00:00:00Z",
        expires_at="2026-09-02T00:00:00Z",
        argus_expires_at=None,
        corporation_id=98000001,
        records={
            5001: CorporationIndustryJobRow(
                corporation_id=98000001,
                activity_id=1,
                blueprint_id=1001,
                blueprint_location_id=60003760,
                blueprint_type_id=34,
                completed_character_id=42,
                completed_date="2026-09-01T00:00:00Z",
                cost=Decimal("123.45"),
                duration=90,
                end_date="2026-09-02T00:00:00Z",
                facility_id=60000001,
                installer_id=43,
                job_id=5001,
                licensed_runs=1,
                location_id=60003760,
                output_location_id=60003800,
                pause_date="2026-09-01T00:00:01Z",
                probability=0.5,
                product_type_id=35,
                runs=1,
                start_date="2026-09-01T00:00:00Z",
                status="active",
                successful_runs=0,
                response_metadata_id=1,
            )
        },
    )


def test_get_corporation_blueprints_returns_dataset() -> None:
    """Blueprint lookup reconstructs metadata and blueprint records keyed by item ID."""
    connection = _make_connection()
    connection.executemany(
        """
        INSERT INTO response_metadata (received_at, expires_at, argus_expires_at)
        VALUES (?, ?, ?)
        """,
        [
            ("2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z", None),
            ("2026-09-03T00:00:00Z", None, "2026-09-04T00:00:00Z"),
        ],
    )
    connection.executemany(
        """
        INSERT INTO get_corporations_corporation_id_blueprints_response (
            response_metadata_id, corporation_id
        ) VALUES (?, ?)
        """,
        [(1, 98000001), (2, 98000002)],
    )
    connection.executemany(
        """
        INSERT INTO corporation_blueprints (
            corporation_id, item_id, type_id, location_id, location_flag,
            quantity, time_efficiency, material_efficiency, runs,
            response_metadata_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (98000001, 10001, 34, 60003760, "Hangar", 1, 1, 2, 3, 1),
            (98000002, 10002, 35, 60003761, "Factory", -1, 0, 0, -1, 2),
        ],
    )

    assert query_helpers.get_corporation_blueprints_responses(connection, None) == [
        CorporationBlueprintsResponse(
            response_metadata_id=1,
            received_at="2026-09-01T00:00:00Z",
            expires_at="2026-09-02T00:00:00Z",
            argus_expires_at=None,
            corporation_id=98000001,
        ),
        CorporationBlueprintsResponse(
            response_metadata_id=2,
            received_at="2026-09-03T00:00:00Z",
            expires_at=None,
            argus_expires_at="2026-09-04T00:00:00Z",
            corporation_id=98000002,
        ),
    ]
    assert query_helpers.get_corporation_blueprints(
        connection, 1
    ) == CorporationBlueprintsDataset(
        response_metadata_id=1,
        received_at="2026-09-01T00:00:00Z",
        expires_at="2026-09-02T00:00:00Z",
        argus_expires_at=None,
        corporation_id=98000001,
        records={
            10001: CorporationBlueprintRecord(
                corporation_id=98000001,
                item_id=10001,
                type_id=34,
                location_id=60003760,
                location_flag="Hangar",
                quantity=1,
                time_efficiency=1,
                material_efficiency=2,
                runs=3,
                response_metadata_id=1,
            )
        },
    )
