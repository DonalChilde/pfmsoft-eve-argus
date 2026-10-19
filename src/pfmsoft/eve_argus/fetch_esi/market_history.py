"""Fetch and update regional market history when stored data expires."""

from functools import partial
from sqlite3 import Connection

from pfmsoft.eve_link import EsiLink, EsiResponse, EsiSchema

from pfmsoft.eve_argus.esi import fetch as EsiFetch
from pfmsoft.eve_argus.esi import validate as EsiValidate
from pfmsoft.eve_argus.fetch_esi.update import UpdateResult, update_if_expired
from pfmsoft.eve_argus.market_history import read, write
from pfmsoft.eve_argus.market_history.models import MarketHistoryResponse

type MarketHistoryUpdateResult = UpdateResult[MarketHistoryResponse]


def _current_state(
    connection: Connection, *, region_id: int, type_id: int
) -> MarketHistoryResponse | None:
    """Return the latest stored response for a region and type."""
    responses = read.read_market_history_responses(
        connection, region_id=region_id, type_id=type_id
    )
    return responses[0] if responses else None


def _store(
    connection: Connection, response: EsiResponse, *, region_id: int, type_id: int
) -> None:
    """Validate and write a market-history response.

    Raises:
        ValueError: If ESI returned a response already stored for this pair.
    """
    history = EsiValidate.market_history(response)
    stored_responses = read.read_market_history_responses(
        connection, region_id=region_id, type_id=type_id
    )
    if any(stored.received_at == history.received_at for stored in stored_responses):
        raise ValueError(
            "ESI returned a previously stored market-history response "
            "without a new received_at."
        )
    write.write_market_history(connection, history=history)


async def update_market_history(
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: Connection,
    *,
    region_id: int,
    type_id: int,
) -> MarketHistoryUpdateResult:
    """Update market history for a region and type when stored data expires.

    Args:
        esi_link: ESI client used to fetch market history.
        schema: Schema used for the ESI request.
        connection: Market-history database connection.
        region_id: Region whose market history is requested.
        type_id: Item type whose market history is requested.

    Returns:
        Update outcome with previous metadata and, on success, new metadata.
        Current data skips fetching. Missing expiration triggers a refresh;
        Argus expiration overrides ESI expiration when present.
    """
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
        store=partial(_store, connection, region_id=region_id, type_id=type_id),
    )
