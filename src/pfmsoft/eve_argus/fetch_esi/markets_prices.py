"""Fetch and update universe market prices when stored data expires."""

from functools import partial
from sqlite3 import Connection

from pfmsoft.eve_link import EsiLink, EsiResponse, EsiSchema

from pfmsoft.eve_argus.dynamic import read, write
from pfmsoft.eve_argus.dynamic.models import MarketsPricesResponse
from pfmsoft.eve_argus.esi import fetch as EsiFetch
from pfmsoft.eve_argus.esi import validate as EsiValidate
from pfmsoft.eve_argus.fetch_esi.update import UpdateResult, update_if_expired

type MarketsPricesUpdateResult = UpdateResult[MarketsPricesResponse]


def _current_state(connection: Connection) -> MarketsPricesResponse | None:
    """Return the latest stored market-prices response, if any."""
    responses = read.markets_prices_responses(connection)
    return responses[0] if responses else None


def _store(connection: Connection, response: EsiResponse) -> None:
    """Validate and write a market-prices response."""
    prices = EsiValidate.markets_prices(response)
    write.markets_prices(connection, markets_prices=prices)


async def update_markets_prices(
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: Connection,
) -> MarketsPricesUpdateResult:
    """Update global market prices when the stored response has expired."""
    return await update_if_expired(
        read_current=partial(_current_state, connection),
        fetch=partial(EsiFetch.markets_prices, esi_link, schema),
        store=partial(_store, connection),
    )
