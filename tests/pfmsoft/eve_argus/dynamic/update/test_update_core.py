"""Tests for the shared update-if-expired workflow."""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from pfmsoft.eve_link import FailedEsiResponse

from pfmsoft.eve_argus.fetch_esi.update import (
    UpdateResult,
    UpdateStatus,
    is_expired,
    update_if_expired,
)


@dataclass(slots=True, kw_only=True)
class _Stored:
    expires_at: str | None
    argus_expires_at: str | None = None


_FUTURE = "2999-01-01T00:00:00Z"
_PAST = "2000-01-01T00:00:00Z"


def test_is_expired() -> None:
    """Missing, past, and unexpirable responses are expired; future ones are not."""
    assert is_expired(None)
    assert is_expired(_Stored(expires_at=None))
    assert is_expired(_Stored(expires_at=_PAST))
    assert not is_expired(_Stored(expires_at=_FUTURE))


def test_is_expired_prefers_argus_expiration() -> None:
    """argus_expires_at overrides the ESI expiration."""
    assert not is_expired(_Stored(expires_at=_PAST, argus_expires_at=_FUTURE))
    assert is_expired(_Stored(expires_at=_FUTURE, argus_expires_at=_PAST))


def test_update_skipped_when_current() -> None:
    """Unexpired data is returned as previous_state without fetching."""
    stored = _Stored(expires_at=_FUTURE)
    fetch = AsyncMock()
    store = MagicMock()

    result = asyncio.run(
        update_if_expired(read_current=lambda: stored, fetch=fetch, store=store)
    )

    assert result == UpdateResult(status=UpdateStatus.SKIPPED, previous_state=stored)
    assert result.succeeded
    fetch.assert_not_awaited()
    store.assert_not_called()


def test_update_stores_and_rereads() -> None:
    """Expired data is refetched, stored, and re-read as new_state."""
    old = _Stored(expires_at=_PAST)
    new = _Stored(expires_at=_FUTURE)
    states = iter([old, new])
    store = MagicMock()

    result = asyncio.run(
        update_if_expired(
            read_current=lambda: next(states),
            fetch=AsyncMock(return_value="raw"),
            store=store,
        )
    )

    store.assert_called_once_with("raw")
    assert result.status is UpdateStatus.UPDATED
    assert result.previous_state is old
    assert result.new_state is new
    assert result.succeeded


@pytest.mark.parametrize(
    ("error_messages", "expected"),
    [
        (["boom"], "boom"),
        (["first failure", "second failure"], "first failure; second failure"),
        (["", "  boom \n", "\t"], "boom"),
        ([], "ESI request failed without an error reason from pfmsoft.api_request."),
        ([""], "ESI request failed without an error reason from pfmsoft.api_request."),
        (
            [" ", "\n", ""],
            "ESI request failed without an error reason from pfmsoft.api_request.",
        ),
    ],
)
def test_update_reports_failed_fetch(
    *, error_messages: list[str], expected: str
) -> None:
    """Report useful reasons or an explicit fallback without list formatting."""
    store = MagicMock()
    response = MagicMock(spec=FailedEsiResponse)
    response.failed_response.error_messages = error_messages

    result = asyncio.run(
        update_if_expired(
            read_current=lambda: None,
            fetch=AsyncMock(return_value=response),
            store=store,
        )
    )

    assert result.status is UpdateStatus.FAILED
    assert result.failure_message == expected
    assert not result.succeeded
    store.assert_not_called()


def test_update_reports_store_exception() -> None:
    """Exceptions raised while storing become a FAILED result."""
    store = MagicMock(side_effect=ValueError("bad data"))

    result = asyncio.run(
        update_if_expired(
            read_current=lambda: None,
            fetch=AsyncMock(return_value="raw"),
            store=store,
        )
    )

    assert result.status is UpdateStatus.FAILED
    assert result.failure_message == "bad data"
    assert result.new_state is None
