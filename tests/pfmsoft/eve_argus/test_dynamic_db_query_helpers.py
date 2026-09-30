"""Tests for dynamic database query helpers."""

import sqlite3

from pfmsoft.eve_argus.dynamic.db import load_table_definitions, query_helpers
from pfmsoft.eve_argus.dynamic.db.models import ResponseMetadata


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
