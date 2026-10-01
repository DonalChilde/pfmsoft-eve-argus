"""Tests for dynamic database query helpers."""

import sqlite3
from dataclasses import replace
from decimal import Decimal

import pytest

from pfmsoft.eve_argus.dynamic.db import load_table_definitions, query_helpers
from pfmsoft.eve_argus.dynamic.db.models import (
    BuySellOrders,
    BuySellSummary,
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
    OrderSummaryDataset,
    OrderSummaryRecord,
    OrderSummaryResponse,
    ResponseMetadata,
    SystemCostIndexRecord,
    SystemCostIndicesDataset,
    SystemCostIndicesResponse,
)
from pfmsoft.eve_argus.models.esi import esi_response_models as ERM


def _make_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(load_table_definitions())
    return connection


def test_market_orders_response_rejects_duplicate_region_timestamp() -> None:
    """Only one source order set per region and receipt time can be stored."""
    connection = _make_connection()
    connection.executemany(
        "INSERT INTO response_metadata (received_at) VALUES (?)",
        [("2026-09-01T00:00:00Z",), ("2026-09-01T00:00:00Z",)],
    )
    connection.execute(
        """
        INSERT INTO get_markets_region_id_orders_response
            (response_metadata_id, region_id, received_at)
        VALUES (1, 10000002, '2026-09-01T00:00:00Z')
        """
    )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO get_markets_region_id_orders_response
                (response_metadata_id, region_id, received_at)
            VALUES (2, 10000002, '2026-09-01T00:00:00Z')
            """
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO get_markets_region_id_orders_response
                (response_metadata_id, region_id, received_at)
            VALUES (2, 10000005, '2026-09-02T00:00:00Z')
            """
        )


def test_write_market_orders_rolls_back_duplicate_response_metadata() -> None:
    """A duplicate order set must not leave a second metadata row behind."""
    connection = _make_connection()
    response = ERM.GetMarketsRegionIdOrders(
        region_id=10000002,
        received_at="2026-09-01T00:00:00Z",
        expires_at=None,
        orders=[],
    )

    query_helpers.write_market_orders(connection, response)
    with pytest.raises(sqlite3.IntegrityError):
        query_helpers.write_market_orders(connection, response)

    assert connection.execute("SELECT count(*) FROM response_metadata").fetchone() == (
        1,
    )


def test_write_market_orders_allows_multiple_sets_per_region() -> None:
    """Distinct response timestamps can coexist within one region."""
    connection = _make_connection()
    response = ERM.GetMarketsRegionIdOrders(
        region_id=10000002,
        received_at="2026-09-01T00:00:00Z",
        expires_at=None,
        orders=[],
    )

    query_helpers.write_market_orders(connection, response)
    query_helpers.write_market_orders(
        connection, replace(response, received_at="2026-09-02T00:00:00Z")
    )

    assert len(query_helpers.get_market_orders_responses(connection, 10000002)) == 2


def test_order_summary_schema_tracks_scopes_and_type_membership() -> None:
    """A source can own different scopes, each with at most one side per type."""
    connection = _make_connection()
    connection.execute(
        "INSERT INTO response_metadata (received_at) VALUES ('2026-09-01T00:00:00Z')"
    )
    connection.execute(
        """INSERT INTO get_markets_region_id_orders_response
           (response_metadata_id, region_id, received_at)
           VALUES (1, 10000002, '2026-09-01T00:00:00Z')"""
    )
    connection.executemany(
        """INSERT INTO order_summary_response
           (response_metadata_id, region_id, system_id, location_id)
           VALUES (?, 10000002, ?, ?)""",
        [(1, None, None), (1, 30000142, None), (1, None, 60003760)],
    )
    connection.execute(
        "INSERT INTO order_summary_types (order_summary_response_id, type_id) VALUES (1, 34)"
    )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """INSERT INTO order_summary_response
               (response_metadata_id, region_id) VALUES (1, 10000002)"""
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """INSERT INTO order_summary_response
               (response_metadata_id, region_id, system_id, location_id)
               VALUES (1, 10000002, 30000142, 60003760)"""
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """INSERT INTO order_summary_response
               (response_metadata_id, region_id) VALUES (1, 10000005)"""
        )


def _insert_source_order_response(connection: sqlite3.Connection) -> None:
    connection.execute(
        """INSERT INTO response_metadata (received_at, expires_at, argus_expires_at)
           VALUES ('2026-09-01T00:00:00Z', '2026-09-02T00:00:00Z', NULL)"""
    )
    connection.execute(
        """INSERT INTO get_markets_region_id_orders_response
           (response_metadata_id, region_id, received_at)
           VALUES (1, 10000002, '2026-09-01T00:00:00Z')"""
    )


def _summary_dataset(
    *,
    system_id: int | None = None,
    location_id: int | None = None,
    records: dict[int, BuySellSummary] | None = None,
) -> OrderSummaryDataset:
    return OrderSummaryDataset(
        response_metadata_id=1,
        received_at="2026-09-01T00:00:00Z",
        expires_at="2026-09-02T00:00:00Z",
        argus_expires_at=None,
        region_id=10000002,
        system_id=system_id,
        location_id=location_id,
        records={} if records is None else records,
    )


def _summary_record(*, is_buy_summary: bool) -> OrderSummaryRecord:
    return OrderSummaryRecord(
        region_id=10000002,
        type_id=34,
        system_id=None,
        location_id=None,
        is_buy_summary=is_buy_summary,
        five_price=Decimal("100.12") if is_buy_summary else Decimal("110.23"),
        five_orders=2,
        five_items=10,
        lowest=Decimal("90.01") if is_buy_summary else Decimal("110.23"),
        highest=Decimal("100.12") if is_buy_summary else Decimal("120.45"),
        total_items=100,
        total_orders=4,
        average=Decimal("95.55") if is_buy_summary else Decimal("115.34"),
        filtered_items=12,
        filtered_orders=1,
    )


def test_write_and_get_order_summaries_round_trip_both_sides() -> None:
    """Saved records use cents and can be reconstructed as a complete dataset."""
    connection = _make_connection()
    _insert_source_order_response(connection)
    dataset = _summary_dataset(
        records={
            34: BuySellSummary(
                buy_summary=_summary_record(is_buy_summary=True),
                sell_summary=_summary_record(is_buy_summary=False),
            )
        }
    )

    batch_id = query_helpers.write_order_summaries(connection, dataset)

    assert isinstance(batch_id, int)
    assert connection.execute(
        "SELECT is_buy_summary, five_price, average FROM order_summaries ORDER BY is_buy_summary"
    ).fetchall() == [(0, 11023, 11534), (1, 10012, 9555)]
    assert connection.execute("SELECT count(*) FROM response_metadata").fetchone() == (
        1,
    )
    assert query_helpers.get_order_summaries(connection, batch_id) == dataset


def test_order_summaries_preserve_empty_and_one_sided_types() -> None:
    """Type membership persists even when no side has positive volume."""
    connection = _make_connection()
    _insert_source_order_response(connection)
    empty = _summary_dataset()

    batch_id = query_helpers.write_order_summaries(connection, empty)

    assert query_helpers.get_order_summaries(connection, batch_id) == empty
    one_side = _summary_dataset(
        records={
            34: BuySellSummary(
                buy_summary=_summary_record(is_buy_summary=True),
                sell_summary=None,
            ),
            35: BuySellSummary(buy_summary=None, sell_summary=None),
        }
    )

    assert query_helpers.write_order_summaries(connection, one_side) == batch_id
    assert query_helpers.get_order_summaries(connection, batch_id) == one_side
    assert connection.execute(
        "SELECT type_id FROM order_summary_types ORDER BY type_id"
    ).fetchall() == [(34,), (35,)]
    assert query_helpers.write_order_summaries(connection, empty) == batch_id
    assert query_helpers.get_order_summaries(connection, batch_id) == empty
    assert connection.execute("SELECT count(*) FROM order_summaries").fetchone() == (0,)


def test_order_summary_responses_discover_independent_scopes() -> None:
    """Each saved scope has a discoverable ID linked to one source response."""
    connection = _make_connection()
    _insert_source_order_response(connection)
    region = _summary_dataset()
    system = _summary_dataset(system_id=30000142)
    location = _summary_dataset(location_id=60003760)
    region_id = query_helpers.write_order_summaries(connection, region)
    system_id = query_helpers.write_order_summaries(connection, system)
    location_id = query_helpers.write_order_summaries(connection, location)

    assert len({region_id, system_id, location_id}) == 3
    assert query_helpers.get_order_summary_responses(connection, 1) == [
        OrderSummaryResponse(
            order_summary_response_id=batch_id,
            response_metadata_id=1,
            received_at="2026-09-01T00:00:00Z",
            expires_at="2026-09-02T00:00:00Z",
            argus_expires_at=None,
            region_id=10000002,
            system_id=scope_system_id,
            location_id=scope_location_id,
        )
        for batch_id, scope_system_id, scope_location_id in (
            (region_id, None, None),
            (system_id, 30000142, None),
            (location_id, None, 60003760),
        )
    ]
    assert query_helpers.get_order_summary_responses(connection, 999) == []
    assert query_helpers.get_order_summaries(connection, system_id) == system
    assert query_helpers.get_order_summaries(connection, region_id) == region
    assert query_helpers.get_order_summaries(connection, location_id) == location


def test_order_summaries_reject_mismatched_source_or_record() -> None:
    """Invalid data does not create or overwrite a saved summary batch."""
    connection = _make_connection()
    _insert_source_order_response(connection)
    original = _summary_dataset(
        records={
            34: BuySellSummary(
                buy_summary=_summary_record(is_buy_summary=True),
                sell_summary=None,
            )
        }
    )
    batch_id = query_helpers.write_order_summaries(connection, original)

    for invalid in (
        replace(original, response_metadata_id=999),
        replace(original, received_at="2026-09-03T00:00:00Z"),
    ):
        with pytest.raises(ValueError):
            query_helpers.write_order_summaries(connection, invalid)

    wrong_side = replace(_summary_record(is_buy_summary=True), is_buy_summary=False)
    with pytest.raises(ValueError, match="does not match"):
        query_helpers.write_order_summaries(
            connection,
            replace(
                original,
                records={34: BuySellSummary(buy_summary=wrong_side, sell_summary=None)},
            ),
        )
    assert query_helpers.get_order_summaries(connection, batch_id) == original
    with pytest.raises(ValueError, match="No order summary response"):
        query_helpers.get_order_summaries(connection, 999)


def test_order_summaries_reject_invalid_scope_type_and_region() -> None:
    """Record and dataset scope mismatches cannot create a saved response."""
    connection = _make_connection()
    _insert_source_order_response(connection)
    record = _summary_record(is_buy_summary=True)
    for invalid in (
        _summary_dataset(system_id=30000142, location_id=60003760),
        replace(_summary_dataset(), region_id=10000005),
        _summary_dataset(
            records={35: BuySellSummary(buy_summary=record, sell_summary=None)}
        ),
        _summary_dataset(
            system_id=30000142,
            records={34: BuySellSummary(buy_summary=record, sell_summary=None)},
        ),
    ):
        with pytest.raises(ValueError):
            query_helpers.write_order_summaries(connection, invalid)
    assert connection.execute(
        "SELECT count(*) FROM order_summary_response"
    ).fetchone() == (0,)


def test_order_summary_replacement_keeps_other_scopes() -> None:
    """Replacing one batch does not change other scopes from the same source."""
    connection = _make_connection()
    _insert_source_order_response(connection)
    region = _summary_dataset(
        records={
            34: BuySellSummary(
                buy_summary=_summary_record(is_buy_summary=True),
                sell_summary=None,
            )
        }
    )
    location_record = replace(
        _summary_record(is_buy_summary=False), location_id=60003760
    )
    location = _summary_dataset(
        location_id=60003760,
        records={34: BuySellSummary(buy_summary=None, sell_summary=location_record)},
    )
    region_id = query_helpers.write_order_summaries(connection, region)
    location_id = query_helpers.write_order_summaries(connection, location)

    assert (
        query_helpers.write_order_summaries(connection, _summary_dataset()) == region_id
    )
    assert (
        query_helpers.get_order_summaries(connection, region_id) == _summary_dataset()
    )
    assert query_helpers.get_order_summaries(connection, location_id) == location


def test_order_summary_schema_rejects_orphan_type_and_duplicate_side() -> None:
    """Foreign keys and the batch/type/side key reject invalid direct inserts."""
    connection = _make_connection()
    _insert_source_order_response(connection)
    dataset = _summary_dataset(
        records={
            34: BuySellSummary(
                buy_summary=_summary_record(is_buy_summary=True),
                sell_summary=None,
            )
        }
    )
    query_helpers.write_order_summaries(connection, dataset)

    assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO order_summary_types VALUES (999, 35)")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO order_summaries (
                order_summary_response_id, region_id, type_id, system_id,
                location_id, is_buy_summary, five_price, five_orders, five_items,
                lowest, highest, average, total_items, total_orders,
                filtered_items, filtered_orders
            ) SELECT order_summary_response_id, region_id, type_id, system_id,
                     location_id, is_buy_summary, five_price, five_orders, five_items,
                     lowest, highest, average, total_items, total_orders,
                     filtered_items, filtered_orders
              FROM order_summaries
            """
        )


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
            response_metadata_id, region_id, received_at
        ) VALUES (?, ?, ?)
        """,
        [
            (1, 10000002, "2026-09-01T00:00:00Z"),
            (2, 10000005, "2026-09-03T00:00:00Z"),
        ],
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
