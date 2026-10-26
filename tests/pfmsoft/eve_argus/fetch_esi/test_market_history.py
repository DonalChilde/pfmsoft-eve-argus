"""Tests for expiry-aware market-history updates."""

import asyncio
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from decimal import Decimal
from typing import Literal
from unittest.mock import AsyncMock, Mock

import pytest
from pfmsoft.eve_link import (
    EsiLink,
    EsiRequest,
    EsiResponse,
    EsiSchema,
    FailedEsiResponse,
)
from whenever import Instant

from pfmsoft.eve_argus.esi.models import GetMarketsRegionIdHistory
from pfmsoft.eve_argus.fetch_esi import update_market_history
from pfmsoft.eve_argus.fetch_esi.update import UpdateStatus
from pfmsoft.eve_argus.market_history import read, util, write

_PAST = "2000-01-01T00:00:00Z"
_FUTURE = "2999-01-01T00:00:00Z"
_RECEIVED = "2026-10-18T00:00:00Z"


@pytest.fixture
def connection() -> Iterator[sqlite3.Connection]:
    """Provide an isolated history database with the production schema."""
    with closing(sqlite3.connect(":memory:")) as database:
        database.executescript(util.load_table_definitions())
        yield database


def _response(
    *,
    received_at: str = _RECEIVED,
    history: list[dict[str, str | int | float]] | None = None,
) -> Mock:
    """Build an ESI response using real request and timestamp objects."""
    response = Mock(spec=EsiResponse)
    response.esi_request = EsiRequest(
        operation_id="GetMarketsRegionIdHistory",
        path_parameters={"region_id": 10},
        query_parameters={"type_id": 20},
    )
    response.response.metadata.received_at = received_at
    response.response.metadata.expires_at_instant = Instant.parse_iso(_FUTURE)
    response.response_data = (
        [
            {
                "average": 123.45,
                "date": "2026-10-17",
                "highest": 130.00,
                "lowest": 120.00,
                "order_count": 5,
                "volume": 100,
            }
        ]
        if history is None
        else history
    )
    return response


def _seed(
    connection: sqlite3.Connection,
    *,
    expires_at: str | None = _PAST,
    argus_expires_at: str | None = None,
    region_id: int = 10,
    type_id: int = 20,
    received_at: str = _PAST,
) -> None:
    """Store metadata for a selected region/type pair."""
    with connection:
        connection.execute(
            """
            INSERT INTO market_history_response
                (received_at, expires_at, argus_expires_at, region_id, type_id,
                    response_count)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (received_at, expires_at, argus_expires_at, region_id, type_id, 1),
        )
        connection.execute(
            """
            INSERT INTO market_history (
                received_at, expires_at, argus_expires_at, region_id, type_id,
                average, date_, highest, lowest, order_count, volume
            )
            VALUES (?, ?, ?, ?, ?, 100, ?, 200, 50, 1, 2)
            """,
            (
                received_at,
                expires_at,
                argus_expires_at,
                region_id,
                type_id,
                received_at[:10],
            ),
        )


def test_update_persists_validated_history(connection: sqlite3.Connection) -> None:
    """A missing pair is fetched, validated, stored, and returned."""
    esi_link = Mock(spec=EsiLink)
    esi_link.make_request = AsyncMock(return_value=_response())
    schema = Mock(spec=EsiSchema)

    result = asyncio.run(
        update_market_history(esi_link, schema, connection, region_id=10, type_id=20)
    )

    assert result.status is UpdateStatus.UPDATED
    assert result.previous_state is None
    assert result.new_state is not None
    assert (
        result.new_state
        == read.market_history_responses(connection, region_id=10, type_id=20, count=1)[
            0
        ]
    )
    assert result.new_state.received_at == _RECEIVED
    assert result.new_state.expires_at == _FUTURE
    request = esi_link.make_request.await_args.kwargs["esi_request"]
    assert request.operation_id == "GetMarketsRegionIdHistory"
    assert request.path_parameters == {"region_id": 10}
    assert request.query_parameters == {"type_id": 20}
    esi_link.make_request.assert_awaited_once_with(esi_request=request, schema=schema)
    record = read.market_history(connection, region_id=10, type_id=20)[0]
    assert record.average == Decimal("123.45")
    assert record.highest == Decimal("130.00")
    assert record.lowest == Decimal("120.00")
    assert (record.date, record.order_count, record.volume) == ("2026-10-17", 5, 100)


@pytest.mark.parametrize("has_history", [False, True])
@pytest.mark.parametrize(
    ("expires_at", "argus_expires_at", "expected"),
    [
        (_FUTURE, None, UpdateStatus.SKIPPED),
        (_PAST, None, UpdateStatus.UPDATED),
        (None, None, UpdateStatus.UPDATED),
        (_PAST, _FUTURE, UpdateStatus.SKIPPED),
        (_FUTURE, _PAST, UpdateStatus.UPDATED),
    ],
)
def test_update_respects_expiration(
    connection: sqlite3.Connection,
    *,
    has_history: bool,
    expires_at: str | None,
    argus_expires_at: str | None,
    expected: UpdateStatus,
) -> None:
    """Argus expiration overrides ESI expiration for the selected pair."""
    _seed(connection, expires_at=expires_at, argus_expires_at=argus_expires_at)
    if not has_history:
        with connection:
            connection.execute("DELETE FROM market_history")
    previous = read.market_history_responses(
        connection, region_id=10, type_id=20, count=1
    )[0]
    esi_link = Mock(spec=EsiLink)
    esi_link.make_request = AsyncMock(return_value=_response())

    result = asyncio.run(
        update_market_history(
            esi_link, Mock(spec=EsiSchema), connection, region_id=10, type_id=20
        )
    )

    assert result.status is expected
    assert result.previous_state == previous
    if expected is UpdateStatus.SKIPPED:
        esi_link.make_request.assert_not_awaited()
        assert result.new_state is None
    else:
        esi_link.make_request.assert_awaited_once()


@pytest.mark.parametrize(
    ("history_expiration", "occurrence_expiration", "expected"),
    [
        (_PAST, _FUTURE, UpdateStatus.SKIPPED),
        (_FUTURE, _PAST, UpdateStatus.UPDATED),
    ],
)
def test_update_uses_response_expiration(
    connection: sqlite3.Connection,
    *,
    history_expiration: str,
    occurrence_expiration: str,
    expected: UpdateStatus,
) -> None:
    """Response expiration controls freshness regardless of history expiration."""
    _seed(connection, expires_at=occurrence_expiration)
    with connection:
        connection.execute(
            "UPDATE market_history SET expires_at = ? WHERE region_id = 10 AND type_id = 20",
            (history_expiration,),
        )
    esi_link = Mock(spec=EsiLink)
    esi_link.make_request = AsyncMock(return_value=_response())

    result = asyncio.run(
        update_market_history(
            esi_link, Mock(spec=EsiSchema), connection, region_id=10, type_id=20
        )
    )

    assert result.status is expected
    if expected is UpdateStatus.SKIPPED:
        esi_link.make_request.assert_not_awaited()
    else:
        esi_link.make_request.assert_awaited_once()


@pytest.mark.parametrize("existing_pair", [False, True])
def test_update_isolates_pairs_and_selects_latest(
    connection: sqlite3.Connection, *, existing_pair: bool
) -> None:
    """Expiry follows the latest received response and ignores other pairs."""
    if existing_pair:
        _seed(connection, expires_at=_FUTURE, received_at="2026-10-02T00:00:00Z")
        _seed(connection, received_at="2026-10-01T00:00:00Z")
    _seed(connection, expires_at=_FUTURE, region_id=11)
    _seed(connection, expires_at=_FUTURE, type_id=21)
    esi_link = Mock(spec=EsiLink)
    esi_link.make_request = AsyncMock(return_value=_response())

    result = asyncio.run(
        update_market_history(
            esi_link, Mock(spec=EsiSchema), connection, region_id=10, type_id=20
        )
    )

    assert result.status is (
        UpdateStatus.SKIPPED if existing_pair else UpdateStatus.UPDATED
    )
    if existing_pair:
        assert result.previous_state is not None
        assert result.previous_state.received_at == "2026-10-02T00:00:00Z"
    else:
        assert result.previous_state is None
    for region_id, type_id in ((11, 20), (10, 21)):
        assert (
            len(
                read.market_history_responses(
                    connection, region_id=region_id, type_id=type_id
                )
            )
            == 1
        )


def test_update_preserves_older_dates(connection: sqlite3.Connection) -> None:
    """Overlapping dates are replaced while dates absent from ESI are retained."""
    old = _response(
        received_at=_PAST,
        history=[
            {
                "average": 1.0,
                "date": date,
                "highest": 2.0,
                "lowest": 0.5,
                "order_count": 1,
                "volume": 2,
            }
            for date in ("2026-10-16", "2026-10-17")
        ],
    )
    write.write_market_history(
        connection,
        history=GetMarketsRegionIdHistory(
            received_at=_PAST,
            expires_at=_PAST,
            region_id=10,
            type_id=20,
            history=old.response_data,
        ),
    )
    esi_link = Mock(spec=EsiLink)
    esi_link.make_request = AsyncMock(return_value=_response())

    result = asyncio.run(
        update_market_history(
            esi_link, Mock(spec=EsiSchema), connection, region_id=10, type_id=20
        )
    )

    assert result.status is UpdateStatus.UPDATED
    records = read.market_history(connection, region_id=10, type_id=20)
    assert [record.date for record in records] == ["2026-10-17", "2026-10-16"]
    assert [record.average for record in records] == [Decimal("123.45"), Decimal("1")]
    assert len(read.market_history_responses(connection, region_id=10, type_id=20)) == 2


def test_update_stores_empty_response(connection: sqlite3.Connection) -> None:
    """Empty history records freshness and skips a second request."""
    esi_link = Mock(spec=EsiLink)
    esi_link.make_request = AsyncMock(return_value=_response(history=[]))

    result = asyncio.run(
        update_market_history(
            esi_link, Mock(spec=EsiSchema), connection, region_id=10, type_id=20
        )
    )

    assert result.status is UpdateStatus.UPDATED
    assert result.new_state is not None
    assert result.new_state.expires_at == _FUTURE
    assert read.market_history(connection, region_id=10, type_id=20) == ()
    assert (
        read.market_history_responses(connection, region_id=10, type_id=20)[
            0
        ].received_at
        == _RECEIVED
    )
    cached = asyncio.run(
        update_market_history(
            esi_link, Mock(spec=EsiSchema), connection, region_id=10, type_id=20
        )
    )
    assert cached.status is UpdateStatus.SKIPPED
    assert cached.previous_state == result.new_state
    esi_link.make_request.assert_awaited_once()


@pytest.mark.parametrize("failure", ["esi", "validation", "write"])
def test_update_reports_failure_without_partial_writes(
    connection: sqlite3.Connection,
    *,
    failure: Literal["esi", "validation", "write"],
) -> None:
    """Failures preserve existing data and report a failed result."""
    _seed(connection)
    previous = read.market_history_responses(connection, region_id=10, type_id=20)
    response = _response()
    match failure:
        case "esi":
            response = Mock(spec=FailedEsiResponse)
            response.failed_response.error_messages = ["ESI unavailable"]
        case "validation":
            response.response_data = [{"average": "invalid"}]
        case "write":
            with connection:
                connection.execute(
                    """
                    INSERT INTO market_history (
                        received_at, region_id, type_id, average, date_,
                        highest, lowest, order_count, volume
                    ) VALUES (?, 10, 20, 100, '2026-10-17', 200, 50, 1, 2)
                    """,
                    (_PAST,),
                )
            response.response_data.append(
                {
                    **response.response_data[0],
                    "date": "2026-10-18",
                }
            )
            connection.executescript(
                """
                CREATE TRIGGER reject_history BEFORE INSERT ON market_history
                WHEN NEW.date_ = '2026-10-18'
                BEGIN
                    SELECT RAISE(ABORT, 'history write rejected');
                END;
                """
            )
    previous_records = read.market_history(connection, region_id=10, type_id=20)
    esi_link = Mock(spec=EsiLink)
    esi_link.make_request = AsyncMock(return_value=response)

    result = asyncio.run(
        update_market_history(
            esi_link, Mock(spec=EsiSchema), connection, region_id=10, type_id=20
        )
    )

    assert result.status is UpdateStatus.FAILED
    assert result.previous_state == previous[0]
    assert result.new_state is None
    assert result.failure_message
    assert (
        read.market_history_responses(connection, region_id=10, type_id=20) == previous
    )
    assert read.market_history(connection, region_id=10, type_id=20) == previous_records


def test_update_reads_only_latest_response_and_replaces_repeat_occurrence(
    connection: sqlite3.Connection,
) -> None:
    """Read only the newest metadata, with no duplicate-existence query."""
    _seed(connection, received_at=_RECEIVED)
    _seed(connection, received_at="2026-10-19T00:00:00Z")
    esi_link = Mock(spec=EsiLink)
    esi_link.make_request = AsyncMock(return_value=_response())
    schema = Mock(spec=EsiSchema)
    statements: list[str] = []
    connection.set_trace_callback(statements.append)

    repeated = asyncio.run(
        update_market_history(esi_link, schema, connection, region_id=10, type_id=20)
    )
    assert repeated.status is UpdateStatus.UPDATED
    assert repeated.previous_state is not None
    assert repeated.previous_state.received_at == "2026-10-19T00:00:00Z"
    queries = [sql for sql in statements if sql.lstrip().startswith("SELECT")]
    assert len(queries) == 2
    assert all(
        "FROM market_history_response\n" in sql and "LIMIT 1" in sql for sql in queries
    )
    assert len(read.market_history_responses(connection, region_id=10, type_id=20)) == 2

    esi_link.make_request.return_value = _response(
        received_at="2026-10-20T00:00:00Z",
        history=[
            {
                "average": 123.45,
                "date": "2026-10-20",
                "highest": 130.00,
                "lowest": 120.00,
                "order_count": 5,
                "volume": 100,
            }
        ],
    )
    updated = asyncio.run(
        update_market_history(esi_link, schema, connection, region_id=10, type_id=20)
    )
    assert updated.status is UpdateStatus.UPDATED
    assert updated.new_state is not None
    assert updated.new_state.received_at == "2026-10-20T00:00:00Z"
