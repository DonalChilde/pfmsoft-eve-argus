"""Tests for system cost indices updates."""

import sqlite3

from pfmsoft.eve_argus.dynamic.models import SystemCostIndicesResponse
from pfmsoft.eve_argus.dynamic.util import load_table_definitions
from pfmsoft.eve_argus.fetch_esi.system_cost_indices import _current_state
from pfmsoft.eve_argus.fetch_esi.update import is_expired


def _make_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(load_table_definitions())
    return connection


def _insert_response(
    connection: sqlite3.Connection, *, received_at: str, expires_at: str
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO response_metadata (received_at, expires_at)
        VALUES (?, ?)
        """,
        (received_at, expires_at),
    )
    response_metadata_id = cursor.lastrowid
    connection.execute(
        """
        INSERT INTO get_industry_systems_response (response_metadata_id)
        VALUES (?)
        """,
        (response_metadata_id,),
    )
    return response_metadata_id


def test_current_state_uses_latest_system_cost_indices_response() -> None:
    """An older expired response must not hide the latest unexpired response."""
    connection = _make_connection()
    _insert_response(
        connection,
        received_at="2026-09-01T00:00:00Z",
        expires_at="2026-09-02T00:00:00Z",
    )
    latest_response_id = _insert_response(
        connection,
        received_at="2026-09-03T00:00:00Z",
        expires_at="2999-01-01T00:00:00Z",
    )

    current = _current_state(connection)

    assert current == SystemCostIndicesResponse(
        response_metadata_id=latest_response_id,
        received_at="2026-09-03T00:00:00Z",
        expires_at="2999-01-01T00:00:00Z",
        argus_expires_at=None,
    )
    assert not is_expired(current)
