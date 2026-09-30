"""Tests for dynamic database query helpers."""

import sqlite3
from decimal import Decimal

from pfmsoft.eve_argus.dynamic.db import load_table_definitions, query_helpers
from pfmsoft.eve_argus.dynamic.db.models import (
    ResponseMetadata,
    UniversePriceDataset,
    UniversePriceRecord,
    UniversePricesResponse,
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


def test_get_universe_prices_responses_returns_linked_metadata() -> None:
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

    assert query_helpers.get_universe_prices_responses(connection) == [
        UniversePricesResponse(
            response_metadata_id=1,
            received_at="2026-09-01T00:00:00Z",
            expires_at="2026-09-02T00:00:00Z",
            argus_expires_at=None,
        )
    ]


def test_get_universe_prices_returns_dataset_and_converts_prices() -> None:
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
        INSERT INTO universe_prices (
            type_id, average_price, adjusted_price, response_metadata_id
        ) VALUES (?, ?, ?, ?)
        """,
        [(34, 12345, 10000, 1), (35, None, 250, 1)],
    )

    assert query_helpers.get_universe_prices(connection, 1) == UniversePriceDataset(
        response_metadata_id=1,
        received_at="2026-09-01T00:00:00Z",
        expires_at="2026-09-02T00:00:00Z",
        argus_expires_at=None,
        records={
            34: UniversePriceRecord(
                type_id=34,
                average_price=Decimal("123.45"),
                adjusted_price=Decimal("100.00"),
                response_metadata_id=1,
            ),
            35: UniversePriceRecord(
                type_id=35,
                average_price=None,
                adjusted_price=Decimal("2.50"),
                response_metadata_id=1,
            ),
        },
    )
