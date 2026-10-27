"""Fetch and update regional market history when stored data expires."""

from functools import partial
from sqlite3 import Connection

from pfmsoft.eve_link import EsiLink, EsiResponse, EsiSchema
from whenever import Instant

from pfmsoft.eve_argus.esi import fetch as EsiFetch
from pfmsoft.eve_argus.esi import validate as EsiValidate
from pfmsoft.eve_argus.fetch_esi.update import (
    UpdateResult,
    UpdateStatus,
    update_if_expired,
)
from pfmsoft.eve_argus.market_history import read, write
from pfmsoft.eve_argus.market_history.models import MarketHistoryResponse

type MarketHistoryUpdateResult = UpdateResult[MarketHistoryResponse]


def _current_state(
    connection: Connection, *, region_id: int, type_id: int
) -> MarketHistoryResponse | None:
    """Return the newest response metadata, including empty history responses."""
    records = read.market_history_responses(
        connection, region_id=region_id, type_id=type_id, count=1
    )
    return records[0] if records else None


def _store(connection: Connection, response: EsiResponse) -> None:
    """Validate and write a market-history response."""
    history = EsiValidate.market_history(response)
    write.write_market_history(connection, history=history)


async def update_market_history(
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: Connection,
    *,
    region_id: int,
    type_id: int,
    stale_after_days: int | None = None,
) -> MarketHistoryUpdateResult:
    """Update market history for a region and type when stored data expires.

    Args:
        esi_link: ESI client used to fetch market history.
        schema: Schema used for the ESI request.
        connection: Market-history database connection.
        region_id: Region whose market history is requested.
        type_id: Item type whose market history is requested.
        stale_after_days: Skip responses no older than this many 24-hour days.
            None or zero disables this additional gate; expiry checks still apply.

    Returns:
        Update outcome with previous metadata and, on success, new metadata.
        Current data skips fetching. Missing expiration triggers a refresh;
        Argus expiration overrides ESI expiration when present. Freshness comes
        from the newest response, even when no history records were returned.

    Raises:
        ValueError: If stale_after_days is negative.
    """
    if stale_after_days is not None and stale_after_days < 0:
        raise ValueError("stale_after_days must be nonnegative")
    if stale_after_days:
        previous = _current_state(connection, region_id=region_id, type_id=type_id)
        if previous is not None:
            age_seconds = (
                Instant.now() - Instant.parse_iso(previous.received_at)
            ).total("seconds")
            if age_seconds <= stale_after_days * 86400:
                return UpdateResult(
                    status=UpdateStatus.SKIPPED, previous_state=previous
                )
    return await update_if_expired(
        read_current=partial(
            _current_state, connection, region_id=region_id, type_id=type_id
        ),
        fetch=partial(
            EsiFetch.market_history,
            esi_link,
            schema,
            region_id=region_id,
            type_id=type_id,
        ),
        store=partial(_store, connection),
    )
