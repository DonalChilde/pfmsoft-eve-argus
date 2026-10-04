"""Fetch and update regional market orders when stored data expires."""

from dataclasses import dataclass
from sqlite3 import Connection

from pfmsoft.eve_link import EsiLink, EsiSchema, FailedEsiResponse
from whenever import Instant

from pfmsoft.eve_argus.data_loaders import esi as FetchEsi
from pfmsoft.eve_argus.dynamic.access import DynamicDBReader, DynamicDBWriter
from pfmsoft.eve_argus.dynamic.db.models import MarketOrdersResponse

_writer = DynamicDBWriter()
_reader = DynamicDBReader()


@dataclass(slots=True, kw_only=True)
class MarketOrdersStatus:
    exists: bool
    expired: bool
    current_state: MarketOrdersResponse | None


@dataclass(slots=True, kw_only=True)
class MarketOrdersUpdateResult:
    update_successful: bool
    update_not_required: bool
    failure_message: str | None
    previous_state: MarketOrdersResponse | None
    new_state: MarketOrdersResponse | None


def _current_state(
    connection: Connection, *, region_id: int
) -> MarketOrdersResponse | None:
    """Return the latest stored market-orders response for a region."""
    responses = _reader.read_market_orders_responses(connection, region_id=region_id)
    return responses[0] if responses else None


def _check_db_status(connection: Connection, *, region_id: int) -> MarketOrdersStatus:
    """Check whether the latest market-orders response for a region has expired."""
    current = _current_state(connection, region_id=region_id)
    expiration = (current.argus_expires_at or current.expires_at) if current else None
    expired = expiration is None or Instant.parse_iso(expiration) <= Instant.now()
    return MarketOrdersStatus(
        exists=current is not None,
        expired=expired,
        current_state=current,
    )


async def _fetch_and_update_market_orders(
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: Connection,
    *,
    region_id: int,
    current_state: MarketOrdersResponse | None,
) -> MarketOrdersUpdateResult:
    """Fetch and persist market orders, preserving the previous state."""
    response = await FetchEsi.fetch_region_market_orders(
        esi_link, schema, region_id=region_id
    )
    if isinstance(response, FailedEsiResponse):
        return MarketOrdersUpdateResult(
            update_successful=False,
            update_not_required=False,
            failure_message=str(response.failed_response.error_messages),
            previous_state=current_state,
            new_state=None,
        )

    try:
        market_orders = FetchEsi.validate_region_market_orders(response)
        stored_responses = _reader.read_market_orders_responses(
            connection, region_id=region_id
        )
        if any(
            stored.received_at == market_orders.received_at
            for stored in stored_responses
        ):
            return MarketOrdersUpdateResult(
                update_successful=False,
                update_not_required=False,
                failure_message=(
                    "ESI returned a previously stored market-orders response "
                    "without a new received_at."
                ),
                previous_state=current_state,
                new_state=None,
            )

        _writer.write_market_orders(connection, market_orders=market_orders)
        new_state = _current_state(connection, region_id=region_id)
    except Exception as error:
        return MarketOrdersUpdateResult(
            update_successful=False,
            update_not_required=False,
            failure_message=str(error),
            previous_state=current_state,
            new_state=None,
        )

    return MarketOrdersUpdateResult(
        update_successful=True,
        update_not_required=False,
        failure_message=None,
        previous_state=current_state,
        new_state=new_state,
    )


async def update_market_orders(
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: Connection,
    *,
    region_id: int,
) -> MarketOrdersUpdateResult:
    """Update a region's market orders when the stored response has expired."""
    status = _check_db_status(connection, region_id=region_id)
    if status.exists and not status.expired:
        return MarketOrdersUpdateResult(
            update_successful=True,
            update_not_required=True,
            failure_message=None,
            previous_state=status.current_state,
            new_state=None,
        )

    return await _fetch_and_update_market_orders(
        esi_link,
        schema,
        connection,
        region_id=region_id,
        current_state=status.current_state,
    )
