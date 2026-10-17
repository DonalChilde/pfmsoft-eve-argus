"""Fetch and update universe market prices when stored data expires."""

from dataclasses import dataclass
from sqlite3 import Connection

from pfmsoft.eve_link import EsiLink, EsiSchema, FailedEsiResponse
from whenever import Instant

from pfmsoft.eve_argus.dynamic import read, write
from pfmsoft.eve_argus.dynamic.models import MarketsPricesResponse
from pfmsoft.eve_argus.esi import fetch as EsiFetch
from pfmsoft.eve_argus.esi import validate as EsiValidate


@dataclass(slots=True, kw_only=True)
class MarketsPricesStatus:
    exists: bool
    expired: bool
    current_state: MarketsPricesResponse | None


@dataclass(slots=True, kw_only=True)
class MarketsPricesUpdateResult:
    update_successful: bool
    update_not_required: bool
    failure_message: str | None
    previous_state: MarketsPricesResponse | None
    new_state: MarketsPricesResponse | None


def _current_state(connection: Connection) -> MarketsPricesResponse | None:
    """Return the latest stored market-prices response, if any."""
    responses = read.markets_prices_responses(connection)
    return responses[0] if responses else None


def _check_db_status(connection: Connection) -> MarketsPricesStatus:
    """Check whether the latest market-prices response has expired."""
    current = _current_state(connection)
    expiration = (current.argus_expires_at or current.expires_at) if current else None
    expired = expiration is None or Instant.parse_iso(expiration) <= Instant.now()
    return MarketsPricesStatus(
        exists=current is not None,
        expired=expired,
        current_state=current,
    )


async def _fetch_and_update_markets_prices(
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: Connection,
    current_state: MarketsPricesResponse | None,
) -> MarketsPricesUpdateResult:
    """Fetch and persist market prices, preserving the previous state."""
    response = await EsiFetch.markets_prices(esi_link, schema)
    if isinstance(response, FailedEsiResponse):
        return MarketsPricesUpdateResult(
            update_successful=False,
            update_not_required=False,
            failure_message=str(response.failed_response.error_messages),
            previous_state=current_state,
            new_state=None,
        )

    try:
        prices = EsiValidate.markets_prices(response)
        write.markets_prices(connection, markets_prices=prices)
        new_state = _current_state(connection)
    except Exception as error:
        return MarketsPricesUpdateResult(
            update_successful=False,
            update_not_required=False,
            failure_message=str(error),
            previous_state=current_state,
            new_state=None,
        )

    return MarketsPricesUpdateResult(
        update_successful=True,
        update_not_required=False,
        failure_message=None,
        previous_state=current_state,
        new_state=new_state,
    )


async def update_markets_prices(
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: Connection,
) -> MarketsPricesUpdateResult:
    """Update global market prices when the stored response has expired."""
    status = _check_db_status(connection)
    if status.exists and not status.expired:
        return MarketsPricesUpdateResult(
            update_successful=True,
            update_not_required=True,
            failure_message=None,
            previous_state=status.current_state,
            new_state=None,
        )

    return await _fetch_and_update_markets_prices(
        esi_link,
        schema,
        connection,
        current_state=status.current_state,
    )
