"""Tests for dynamic database query helpers."""

import sqlite3
from decimal import Decimal

from pfmsoft.eve_argus.dynamic.db import load_table_definitions, query_helpers
from pfmsoft.eve_argus.dynamic.db.models import (
    BuySellOrders,
    MarketOrderRecord,
    MarketOrdersDataset,
    MarketOrdersResponse,
    MarketsPriceRecord,
    MarketsPricesDataset,
    MarketsPricesResponse,
    ResponseMetadata,
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
