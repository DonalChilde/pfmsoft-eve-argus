"""Shared update-if-expired workflow for ESI data stored in Argus databases."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pfmsoft.eve_link import FailedEsiResponse
from whenever import Instant


class UpdateStatus(StrEnum):
    """Outcome of an update attempt."""

    UPDATED = "updated"
    """New data was fetched and stored."""
    SKIPPED = "skipped"
    """Stored data has not expired, so no update was needed."""
    FAILED = "failed"
    """The fetch, validation, or storage step failed."""


@dataclass(slots=True, kw_only=True)
class UpdateResult[T]:
    """Result of an update-if-expired operation.

    Attributes:
        status: The outcome of the update.
        previous_state: The stored response before the update, if any.
        new_state: The stored response after a successful update, otherwise None.
        failure_message: Description of the failure when status is FAILED.
    """

    status: UpdateStatus
    previous_state: T | None
    new_state: T | None = None
    failure_message: str | None = None

    @property
    def succeeded(self) -> bool:
        """Whether the data is current, either updated or already up to date."""
        return self.status is not UpdateStatus.FAILED


class Expirable(Protocol):
    """A stored response with expiration timestamps."""

    @property
    def expires_at(self) -> str | None:
        """ESI expiration timestamp."""
        ...

    @property
    def argus_expires_at(self) -> str | None:
        """Argus-specific expiration timestamp, which overrides expires_at."""
        ...


def is_expired(current: Expirable | None) -> bool:
    """Check whether a stored response is missing or past its expiration.

    Args:
        current: The latest stored response, or None if nothing is stored.
    """
    if current is None:
        return True
    expiration = current.argus_expires_at or current.expires_at
    return expiration is None or Instant.parse_iso(expiration) <= Instant.now()


async def update_if_expired[T: Expirable, R](
    *,
    read_current: Callable[[], T | None],
    fetch: Callable[[], Awaitable[R | FailedEsiResponse]],
    store: Callable[[R], None],
) -> UpdateResult[T]:
    """Fetch and store new data only when the stored response has expired.

    Args:
        read_current: Returns the latest stored response, or None.
        fetch: Fetches fresh data from ESI.
        store: Validates and writes a successful ESI response. Any exception it
            raises is reported as a failed update.
    """
    previous = read_current()
    if not is_expired(previous):
        return UpdateResult(status=UpdateStatus.SKIPPED, previous_state=previous)

    response = await fetch()
    if isinstance(response, FailedEsiResponse):
        return UpdateResult(
            status=UpdateStatus.FAILED,
            previous_state=previous,
            failure_message=str(response.failed_response.error_messages),
        )

    try:
        store(response)
        new_state = read_current()
    except Exception as error:
        return UpdateResult(
            status=UpdateStatus.FAILED,
            previous_state=previous,
            failure_message=str(error),
        )
    return UpdateResult(
        status=UpdateStatus.UPDATED, previous_state=previous, new_state=new_state
    )
