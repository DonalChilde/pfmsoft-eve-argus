"""Fetch and update regional market orders when stored data expires."""

from functools import partial
from sqlite3 import Connection

from pfmsoft.eve_link import EsiLink, EsiResponse, EsiSchema

from pfmsoft.eve_argus.dynamic import read, write
from pfmsoft.eve_argus.dynamic.models import MarketOrdersResponse
from pfmsoft.eve_argus.esi import fetch as EsiFetch
from pfmsoft.eve_argus.esi import validate as EsiValidate
from pfmsoft.eve_argus.fetch_esi.update import UpdateResult, update_if_expired

type MarketOrdersUpdateResult = UpdateResult[MarketOrdersResponse]


def _current_state(
    connection: Connection, *, region_id: int
) -> MarketOrdersResponse | None:
    """Return the latest stored market-orders response for a region."""
    responses = read.market_orders_responses(connection, region_id=region_id)
    return responses[0] if responses else None


def _store(connection: Connection, response: EsiResponse, *, region_id: int) -> None:
    """Validate and write a market-orders response.

    Raises:
        ValueError: If ESI returned a response already stored for this region.
    """
    market_orders = EsiValidate.region_market_orders(response)
    stored_responses = read.market_orders_responses(connection, region_id=region_id)
    if any(
        stored.received_at == market_orders.received_at for stored in stored_responses
    ):
        raise ValueError(
            "ESI returned a previously stored market-orders response "
            "without a new received_at."
        )
    write.market_orders(connection, market_orders=market_orders)


async def update_market_orders(
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: Connection,
    *,
    region_id: int,
) -> MarketOrdersUpdateResult:
    """Update a region's market orders when the stored response has expired."""
    return await update_if_expired(
        read_current=partial(_current_state, connection, region_id=region_id),
        fetch=partial(
            EsiFetch.region_market_orders, esi_link, schema, region_id=region_id
        ),
        store=partial(_store, connection, region_id=region_id),
    )
