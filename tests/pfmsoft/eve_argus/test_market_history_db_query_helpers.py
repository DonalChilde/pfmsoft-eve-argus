"""Tests for market-history database query helpers."""

import sqlite3
from decimal import Decimal

import pytest

from pfmsoft.eve_argus.market.history.db import models, query_helpers


def test_read_market_history_filters_and_orders_records() -> None:
    """Read matching history newest first and convert prices from cents."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(query_helpers.load_table_definitions())
    connection.executemany(
        """
        INSERT INTO market_history (
            received_at, region_id, type_id, average, date_, highest, lowest,
            order_count, volume
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("2026-10-01", 10, 20, 12345, "2026-09-30", 13000, 12000, 5, 100),
            ("2026-10-01", 10, 20, 11000, "2026-09-29", 11500, 10500, 3, 80),
            ("2026-10-01", 10, 21, 99900, "2026-10-01", 100000, 99000, 9, 70),
            ("2026-10-01", 11, 20, 88800, "2026-10-01", 89000, 87000, 8, 60),
        ],
    )

    records = query_helpers.read_market_history(connection, region_id=10, type_id=20)

    assert records == (
        models.MarketHistoryRecord(
            received_at="2026-10-01",
            region_id=10,
            type_id=20,
            average=Decimal("123.45"),
            date="2026-09-30",
            highest=Decimal("130.00"),
            lowest=Decimal("120.00"),
            order_count=5,
            volume=100,
        ),
        models.MarketHistoryRecord(
            received_at="2026-10-01",
            region_id=10,
            type_id=20,
            average=Decimal("110.00"),
            date="2026-09-29",
            highest=Decimal("115.00"),
            lowest=Decimal("105.00"),
            order_count=3,
            volume=80,
        ),
    )

    bounded_records = query_helpers.read_market_history_date_range(
        connection,
        region_id=10,
        type_id=20,
        start="2026-09-30",
        end="2026-09-29",
    )
    assert bounded_records == records

    assert [
        record.date
        for record in query_helpers.read_market_history_date_range(
            connection,
            region_id=10,
            type_id=20,
            start="2026-09-29",
            end=None,
        )
    ] == ["2026-09-29"]
    assert [
        record.date
        for record in query_helpers.read_market_history_date_range(
            connection,
            region_id=10,
            type_id=20,
            start=None,
            end="2026-09-30",
        )
    ] == ["2026-09-30"]
    assert [
        record.date
        for record in query_helpers.read_market_history_date_range(
            connection,
            region_id=10,
            type_id=20,
            start=None,
            end=None,
        )
    ] == ["2026-09-30", "2026-09-29"]

    assert query_helpers.read_market_history_latest(
        connection, region_id=10, type_id=20, count=1
    ) == (records[0],)
    with pytest.raises(ValueError, match="count must be positive"):
        query_helpers.read_market_history_latest(
            connection, region_id=10, type_id=20, count=0
        )
    with pytest.raises(ValueError, match="count must be positive"):
        query_helpers.read_market_history_latest(
            connection, region_id=10, type_id=20, count=-1
        )


def test_read_market_history_responses_filter_order_and_group_by_region() -> None:
    """Read response metadata newest first and group region data by type."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(query_helpers.load_table_definitions())
    connection.executemany(
        """
        INSERT INTO market_history_response (
            received_at, expires_at, argus_expires_at, region_id, type_id
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("2026-10-01", "2026-10-02", None, 10, 20),
            ("2026-10-02", None, "2026-10-03", 10, 20),
            ("2026-10-03", "2026-10-04", None, 10, 21),
            ("2026-10-04", None, None, 11, 20),
        ],
    )

    responses = query_helpers.read_market_history_responses(
        connection, region_id=10, type_id=20
    )

    assert responses == (
        models.MarketHistoryResponse(
            response_metadata_id=2,
            received_at="2026-10-02",
            expires_at=None,
            argus_expires_at="2026-10-03",
            region_id=10,
            type_id=20,
        ),
        models.MarketHistoryResponse(
            response_metadata_id=1,
            received_at="2026-10-01",
            expires_at="2026-10-02",
            argus_expires_at=None,
            region_id=10,
            type_id=20,
        ),
    )

    assert query_helpers.read_market_history_responses_by_region(
        connection, region_id=10
    ) == {
        20: responses,
        21: (
            models.MarketHistoryResponse(
                response_metadata_id=3,
                received_at="2026-10-03",
                expires_at="2026-10-04",
                argus_expires_at=None,
                region_id=10,
                type_id=21,
            ),
        ),
    }
