"""Tests for market-history database readers."""

import sqlite3
from contextlib import closing
from decimal import Decimal

import pytest

from pfmsoft.eve_argus.market_history import models, read, util


def test_targeted_response_queries() -> None:
    """Find only the newest pair metadata and exact duplicate timestamps."""
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.executescript(util.load_table_definitions())
        connection.executemany(
            """
            INSERT INTO market_history_response
                (received_at, expires_at, argus_expires_at, region_id, type_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("2026-10-02", None, "2026-10-03", 10, 20),
                ("2026-10-01", "2026-10-02", None, 10, 20),
                ("2026-10-04", None, None, 11, 20),
                ("2026-10-05", None, None, 10, 21),
            ],
        )
        statements: list[str] = []
        connection.set_trace_callback(statements.append)
        assert read.read_market_history_latest_response(
            connection, region_id=10, type_id=20
        ) == models.MarketHistoryResponse(
            response_metadata_id=1,
            received_at="2026-10-02",
            expires_at=None,
            argus_expires_at="2026-10-03",
            region_id=10,
            type_id=20,
        )
        latest_query = next(sql for sql in statements if "SELECT" in sql)
        assert "LIMIT 1" in latest_query
        plan = [
            row[3] for row in connection.execute("EXPLAIN QUERY PLAN " + latest_query)
        ]
        assert any(
            "SEARCH" in step and "market_history_response_pair_received" in step
            for step in plan
        )
        assert not any("SCAN" in step or "TEMP B-TREE" in step for step in plan)
        assert (
            read.read_market_history_latest_response(
                connection, region_id=99, type_id=20
            )
            is None
        )
        statements.clear()
        assert read.market_history_response_exists(
            connection, region_id=10, type_id=20, received_at="2026-10-01"
        )
        exists_query = next(sql for sql in statements if "SELECT" in sql)
        assert "EXISTS" in exists_query
        plan = [
            row[3] for row in connection.execute("EXPLAIN QUERY PLAN " + exists_query)
        ]
        assert any("SEARCH market_history_response" in step for step in plan)
        for region_id, type_id, received_at in (
            (11, 20, "2026-10-01"),
            (10, 21, "2026-10-01"),
            (10, 20, "2026-10-06"),
        ):
            assert not read.market_history_response_exists(
                connection,
                region_id=region_id,
                type_id=type_id,
                received_at=received_at,
            )


def test_schema_adds_index_to_existing_database() -> None:
    """Schema initialization adds the index idempotently without losing metadata."""
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.executescript(
            """
            CREATE TABLE market_history_response (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                received_at TEXT NOT NULL,
                expires_at TEXT,
                argus_expires_at TEXT,
                region_id INTEGER NOT NULL,
                type_id INTEGER NOT NULL,
                UNIQUE(received_at, region_id, type_id)
            ) STRICT;
            INSERT INTO market_history_response
                (received_at, region_id, type_id) VALUES ('2026-10-01', 10, 20);
            """
        )
        connection.executescript(util.load_table_definitions())
        connection.executescript(util.load_table_definitions())
        assert connection.execute(
            "SELECT received_at, region_id, type_id FROM market_history_response"
        ).fetchall() == [("2026-10-01", 10, 20)]
        assert connection.execute(
            "PRAGMA index_info(market_history_response_pair_received)"
        ).fetchall() == [
            (0, 4, "region_id"),
            (1, 5, "type_id"),
            (2, 1, "received_at"),
            (3, 0, "id"),
        ]


def test_read_market_history_filters_and_orders_records() -> None:
    """Read matching history newest first and convert prices from cents."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(util.load_table_definitions())
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

    records = read.read_market_history(connection, region_id=10, type_id=20)

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

    bounded_records = read.read_market_history_date_range(
        connection,
        region_id=10,
        type_id=20,
        start="2026-09-30",
        end="2026-09-29",
    )
    assert bounded_records == records

    assert [
        record.date
        for record in read.read_market_history_date_range(
            connection,
            region_id=10,
            type_id=20,
            start="2026-09-29",
            end=None,
        )
    ] == ["2026-09-29"]
    assert [
        record.date
        for record in read.read_market_history_date_range(
            connection,
            region_id=10,
            type_id=20,
            start=None,
            end="2026-09-30",
        )
    ] == ["2026-09-30"]
    assert [
        record.date
        for record in read.read_market_history_date_range(
            connection,
            region_id=10,
            type_id=20,
            start=None,
            end=None,
        )
    ] == ["2026-09-30", "2026-09-29"]

    assert [
        record.date
        for record in read.read_market_history_date_count(
            connection, region_id=10, type_id=20
        )
    ] == ["2026-09-30", "2026-09-29"]
    assert [
        record.date
        for record in read.read_market_history_date_count(
            connection,
            region_id=10,
            type_id=20,
            start="2026-09-30",
            count=1,
        )
    ] == ["2026-09-30"]
    assert [
        record.date
        for record in read.read_market_history_date_count(
            connection,
            region_id=10,
            type_id=20,
            start="2026-09-29",
            count=2,
        )
    ] == ["2026-09-29"]
    assert (
        read.read_market_history_date_count(
            connection,
            region_id=10,
            type_id=20,
            start="2026-09-28",
            count=5,
        )
        == ()
    )

    plan = [
        row[3]
        for row in connection.execute(
            """
            EXPLAIN QUERY PLAN
            SELECT received_at, region_id, type_id, average, date_, highest,
                lowest, order_count, volume
            FROM market_history
            WHERE region_id = ? AND type_id = ? AND date_ <= ?
            ORDER BY date_ DESC
            LIMIT ?
            """,
            (10, 20, "2026-09-30", 1),
        )
    ]
    assert any("SEARCH market_history USING INDEX" in step for step in plan)
    assert not any("TEMP B-TREE" in step for step in plan)

    assert read.read_market_history_latest(
        connection, region_id=10, type_id=20, count=1
    ) == (records[0],)
    with pytest.raises(ValueError, match="count must be positive"):
        read.read_market_history_latest(connection, region_id=10, type_id=20, count=0)
    with pytest.raises(ValueError, match="count must be positive"):
        read.read_market_history_latest(connection, region_id=10, type_id=20, count=-1)
    with pytest.raises(ValueError, match="count must be positive"):
        read.read_market_history_date_count(
            connection, region_id=10, type_id=20, count=0
        )
    with pytest.raises(ValueError, match="count must be positive"):
        read.read_market_history_date_count(
            connection, region_id=10, type_id=20, count=-1
        )


def test_read_market_history_responses_filter_order_and_group_by_region() -> None:
    """Read response metadata newest first and group region data by type."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(util.load_table_definitions())
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

    responses = read.read_market_history_responses(connection, region_id=10, type_id=20)

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

    assert read.read_market_history_responses_by_region(connection, region_id=10) == {
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
