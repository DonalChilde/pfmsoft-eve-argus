"""Tests for market-history database readers."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from decimal import Decimal

import pytest

from pfmsoft.eve_argus.market_history import models, read, util


@pytest.fixture
def connection() -> Iterator[sqlite3.Connection]:
    """Provide a schema-initialized database and close it after the test."""
    with closing(sqlite3.connect(":memory:")) as database:
        database.executescript(util.load_table_definitions())
        yield database


@pytest.mark.parametrize("count", [None, 1, 2, 10])
@pytest.mark.parametrize("start", [None, "2026-10-02", "2026-10-01", "2026-09-30"])
def test_read_market_history_limits_matching_pair(
    *, start: str | None, count: int | None
) -> None:
    """Filter one pair before applying inclusive date bounds and SQL limits."""
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.executescript(util.load_table_definitions())
        connection.executemany(
            """
            INSERT INTO market_history (
                received_at, expires_at, argus_expires_at, region_id, type_id,
                average, date_, highest, lowest, order_count, volume
            )
            VALUES ('2026-10-05', '2026-10-06', '2026-10-07', ?, ?,
                12345, ?, 13000, 12000, 5, 100)
            """,
            [
                (10, 20, "2026-10-01"),
                (11, 20, "2026-10-03"),
                (10, 21, "2026-10-03"),
                (10, 20, "2026-10-03"),
                (10, 20, "2026-10-02"),
            ],
        )

        records = read.read_market_history(
            connection, region_id=10, type_id=20, start=start, count=count
        )

        expected_dates = [
            date
            for date in ("2026-10-03", "2026-10-02", "2026-10-01")
            if start is None or date <= start
        ][:count]
        assert isinstance(records, tuple)
        assert [record.date for record in records] == expected_dates
        for record in records:
            assert record == models.MarketHistoryRecord(
                received_at="2026-10-05",
                expires_at="2026-10-06",
                argus_expires_at="2026-10-07",
                region_id=10,
                type_id=20,
                average=Decimal("123.45"),
                date=record.date,
                highest=Decimal("130.00"),
                lowest=Decimal("120.00"),
                order_count=5,
                volume=100,
            )
        assert (
            read.read_market_history(
                connection, region_id=99, type_id=20, start=start, count=count
            )
            == ()
        )


@pytest.mark.parametrize(
    ("start", "end", "expected_dates"),
    [
        (None, None, ["2026-10-03", "2026-10-02", "2026-10-01"]),
        ("2026-10-02", None, ["2026-10-02", "2026-10-01"]),
        (None, "2026-10-02", ["2026-10-03", "2026-10-02"]),
        ("2026-10-02", "2026-10-02", ["2026-10-02"]),
        ("2026-10-01", "2026-10-03", []),
        ("2026-09-30", None, []),
        (None, "2026-10-04", []),
    ],
)
def test_read_market_history_date_range_bounds(
    *, start: str | None, end: str | None, expected_dates: list[str]
) -> None:
    """Date ranges are inclusive and do not include records from other pairs."""
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.executescript(util.load_table_definitions())
        connection.executemany(
            """
            INSERT INTO market_history (
                received_at, region_id, type_id, average, date_, highest,
                lowest, order_count, volume
            )
            VALUES ('2026-10-05', ?, ?, 100, ?, 200, 50, 1, 2)
            """,
            [
                (10, 20, "2026-10-01"),
                (10, 20, "2026-10-03"),
                (10, 20, "2026-10-02"),
                (11, 20, "2026-10-02"),
                (10, 21, "2026-10-02"),
            ],
        )

        records = read.read_market_history_date_range(
            connection, region_id=10, type_id=20, start=start, end=end
        )

        assert isinstance(records, tuple)
        assert [record.date for record in records] == expected_dates
        assert all(
            record.region_id == 10 and record.type_id == 20 for record in records
        )


@pytest.mark.parametrize("count", [None, 1, 2, 10])
@pytest.mark.parametrize("start", [None, "2026-10-02", "2026-10-01", "2026-09-30"])
def test_read_market_history_by_region(*, start: str | None, count: int | None) -> None:
    """Filter dates before limiting each type and preserve complete record data."""
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.executescript(util.load_table_definitions())
        connection.executemany(
            """
            INSERT INTO market_history (
                received_at, expires_at, argus_expires_at, region_id, type_id,
                average, date_, highest, lowest, order_count, volume
            )
            VALUES ('2026-10-05', '2026-10-06', '2026-10-07', ?, ?,
                12345, ?, 13000, 12000, 5, 100)
            """,
            [
                (10, 20, "2026-10-01"),
                (11, 20, "2026-10-02"),
                (10, 21, "2026-10-03"),
                (10, 20, "2026-10-02"),
                (10, 21, "2026-10-01"),
            ],
        )

        records = read.read_market_history_by_region(
            connection, region_id=10, start=start, count=count
        )

        expected: dict[int, tuple[models.MarketHistoryRecord, ...]] = {}
        for type_id, dates in (
            (20, ["2026-10-02", "2026-10-01"]),
            (21, ["2026-10-03", "2026-10-01"]),
        ):
            selected_dates = [date for date in dates if start is None or date <= start][
                :count
            ]
            if selected_dates:
                expected[type_id] = tuple(
                    models.MarketHistoryRecord(
                        received_at="2026-10-05",
                        expires_at="2026-10-06",
                        argus_expires_at="2026-10-07",
                        region_id=10,
                        type_id=type_id,
                        average=Decimal("123.45"),
                        date=date,
                        highest=Decimal("130.00"),
                        lowest=Decimal("120.00"),
                        order_count=5,
                        volume=100,
                    )
                    for date in selected_dates
                )
        assert records == expected
        assert (
            read.read_market_history_by_region(
                connection, region_id=99, start=start, count=count
            )
            == {}
        )


@pytest.mark.parametrize("count", [0, -1])
def test_read_market_history_by_region_rejects_nonpositive_count(count: int) -> None:
    """Reject invalid per-type limits even when the database has no history."""
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.executescript(util.load_table_definitions())
        with pytest.raises(ValueError, match="count must be positive"):
            read.read_market_history_by_region(connection, region_id=10, count=count)


def test_read_market_history_responses_uses_pair_index() -> None:
    """Read the newest response using the pair index without a temporary sort."""
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
        assert read.read_market_history_responses(
            connection, region_id=10, type_id=20, count=1
        ) == (
            models.MarketHistoryResponse(
                response_metadata_id=1,
                received_at="2026-10-02",
                expires_at=None,
                argus_expires_at="2026-10-03",
                region_id=10,
                type_id=20,
            ),
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


def test_read_market_history_filters_and_orders_records(
    connection: sqlite3.Connection,
) -> None:
    """Read matching history newest first and convert prices from cents."""
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
            expires_at=None,
            argus_expires_at=None,
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
            expires_at=None,
            argus_expires_at=None,
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

    assert (
        read.read_market_history_date_range(
            connection,
            region_id=10,
            type_id=20,
            start="2026-09-30",
            end="2026-09-29",
        )
        == records
    )

    statements: list[str] = []
    connection.set_trace_callback(statements.append)
    assert read.read_market_history(
        connection, region_id=10, type_id=20, start="2026-09-30", count=1
    ) == (records[0],)
    query = next(sql for sql in statements if "SELECT" in sql)
    assert "LIMIT 1" in query
    plan = [row[3] for row in connection.execute("EXPLAIN QUERY PLAN " + query)]
    assert any("SEARCH market_history USING INDEX" in step for step in plan)
    assert not any("TEMP B-TREE" in step for step in plan)


@pytest.mark.parametrize("count", [0, -1])
def test_read_market_history_rejects_nonpositive_count(count: int) -> None:
    """Reject nonpositive limits using the current pair reader."""
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.executescript(util.load_table_definitions())
        with pytest.raises(ValueError, match="count must be positive"):
            read.read_market_history(connection, region_id=10, type_id=20, count=count)


@pytest.mark.parametrize("count", [None, 1, 2, 10])
def test_read_market_history_responses_limits_records(count: int | None) -> None:
    """Apply the optional limit in SQL without changing pair filtering or order."""
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.executescript(util.load_table_definitions())
        connection.executemany(
            """
            INSERT INTO market_history_response (received_at, region_id, type_id)
            VALUES (?, ?, ?)
            """,
            [
                ("2026-10-01", 10, 20),
                ("2026-10-03", 11, 20),
                ("2026-10-02", 10, 20),
                ("2026-10-04", 10, 21),
            ],
        )
        statements: list[str] = []
        connection.set_trace_callback(statements.append)

        responses = read.read_market_history_responses(
            connection, region_id=10, type_id=20, count=count
        )

        expected = ["2026-10-02", "2026-10-01"]
        assert [response.received_at for response in responses] == expected[:count]
        query = next(sql for sql in statements if "SELECT" in sql)
        if count is None:
            assert "LIMIT" not in query
        else:
            assert f"LIMIT {count}" in query
        assert (
            read.read_market_history_responses(
                connection, region_id=99, type_id=20, count=count
            )
            == ()
        )


@pytest.mark.parametrize("count", [0, -1])
def test_read_market_history_responses_rejects_nonpositive_count(count: int) -> None:
    """Reject invalid limits rather than returning misleading query results."""
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.executescript(util.load_table_definitions())
        with pytest.raises(ValueError, match="count must be positive"):
            read.read_market_history_responses(
                connection, region_id=10, type_id=20, count=count
            )


@pytest.mark.parametrize("count", [None, 1, 2, 10])
def test_read_market_history_responses_by_region_limits_each_type(
    count: int | None,
) -> None:
    """Limit each type independently while preserving newest-first ordering."""
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.executescript(util.load_table_definitions())
        connection.executemany(
            """
            INSERT INTO market_history_response (received_at, region_id, type_id)
            VALUES (?, ?, ?)
            """,
            [
                ("2026-10-01", 10, 20),
                ("2026-10-03", 11, 20),
                ("2026-10-02", 10, 20),
                ("2026-10-04", 10, 21),
                ("2026-10-03", 10, 21),
            ],
        )

        responses = read.read_market_history_responses_by_region(
            connection, region_id=10, count=count
        )

        assert {
            type_id: [response.received_at for response in records]
            for type_id, records in responses.items()
        } == {
            20: ["2026-10-02", "2026-10-01"][:count],
            21: ["2026-10-04", "2026-10-03"][:count],
        }
        assert (
            read.read_market_history_responses_by_region(
                connection, region_id=99, count=count
            )
            == {}
        )


@pytest.mark.parametrize("count", [0, -1])
def test_read_market_history_responses_by_region_rejects_nonpositive_count(
    count: int,
) -> None:
    """Reject nonpositive per-type limits."""
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.executescript(util.load_table_definitions())
        with pytest.raises(ValueError, match="count must be positive"):
            read.read_market_history_responses_by_region(
                connection, region_id=10, count=count
            )


def test_read_market_history_responses_filter_order_and_group_by_region(
    connection: sqlite3.Connection,
) -> None:
    """Read response metadata newest first and group region data by type."""
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
