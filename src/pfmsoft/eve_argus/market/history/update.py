"""Update market history data for items."""

import asyncio
import logging
from dataclasses import dataclass
from sqlite3 import Connection

from pfmsoft.eve_link import (
    EsiLink,
    EsiSchema,
    FailedEsiResponse,
)
from whenever import Instant

from pfmsoft.eve_argus.data_loaders import esi as FetchEsi
from pfmsoft.eve_argus.helpers.timing import log_timing
from pfmsoft.eve_argus.market.history.access import (
    MarketHistoryReader,
    MarketHistoryWrite,
)
from pfmsoft.eve_argus.market.history.db.models import MarketHistoryResponse

logger = logging.getLogger(__name__)
_timing_log_level = logging.INFO

_writer = MarketHistoryWrite()
_reader = MarketHistoryReader()
# Flow for updating item history
# - Check that the latest history data in the database is expired before making an esi-link request.
#   - Even though esi-link should cache responses, we still check expiration at this level. This allows us the most granular control.
# - If expired, fetch new data and update the database.
# - report back the status of each update.
# - Accept requests for multiple updates. possibly as tuple[region_id,type_id] sets.
# - Allow for multiple async tasks for updates. Ensure this flow works with esi-link such that
#   caching and rate limiting work as expected.
# - Handle errors gracefully and retry if needed. TBD what does a time out error look like in esi-link. Does it need to support custom timeouts? Or is it easier just to retry?


@dataclass(slots=True, kw_only=True, frozen=True)
class MarketHistoryID:
    region_id: int
    type_id: int


@dataclass(slots=True, kw_only=True)
class MarketHistoryUpdateResult:
    """Result of an update."""

    # placeholder dataclass, fields to be updated as flow develops
    market_history_id: MarketHistoryID
    update_successful: bool
    update_not_required: bool
    failure_message: str | None
    previous_state: MarketHistoryResponse | None
    new_state: MarketHistoryResponse | None


@dataclass(slots=True, kw_only=True, frozen=True)
class MarketHistoryDBStatus:
    """Database status for market history."""

    market_history_id: MarketHistoryID
    exists: bool
    expired: bool
    current_state: MarketHistoryResponse | None


def _current_state(
    connection: Connection, market_history_id: MarketHistoryID
) -> MarketHistoryResponse | None:
    states = _reader.read_market_history_responses(
        connection,
        region_id=market_history_id.region_id,
        type_id=market_history_id.type_id,
    )
    return states[0] if states else None


async def _fetch_and_update_history(
    esi_link: EsiLink,
    esi_schema: EsiSchema,
    connection: Connection,
    market_history_id: MarketHistoryID,
    current_state: MarketHistoryResponse | None,
) -> MarketHistoryUpdateResult:
    """Update market history for an item.

    Checks if history is expired and updates it.

    This function does not check to see if the current database data is eligible for update.
    It only makes the request and updates the data.

    Args:
        esi_link: The ESI link instance.
        esi_schema: The ESI schema.
        connection: Market history database connection.
        market_history_id: MarketHistoryID.
        current_state: Latest stored response, if one exists.

    Returns:
        MarketHistoryUpdateResult indicating success or failure.
    """
    response = await FetchEsi.fetch_market_history(
        esi_link,
        esi_schema,
        region_id=market_history_id.region_id,
        type_id=market_history_id.type_id,
    )
    if isinstance(response, FailedEsiResponse):
        return MarketHistoryUpdateResult(
            market_history_id=market_history_id,
            update_successful=False,
            update_not_required=False,
            failure_message=str(response.failed_response.error_messages),
            previous_state=current_state,
            new_state=None,
        )
    try:
        history = FetchEsi.validate_market_history(response)
        _writer.write_market_history(connection, history)
        new_state = _current_state(connection, market_history_id)
    except Exception as e:
        return MarketHistoryUpdateResult(
            market_history_id=market_history_id,
            update_successful=False,
            update_not_required=False,
            failure_message=str(e),
            previous_state=current_state,
            new_state=None,
        )
    return MarketHistoryUpdateResult(
        market_history_id=market_history_id,
        update_successful=True,
        update_not_required=False,
        failure_message=None,
        previous_state=current_state,
        new_state=new_state,
    )


@log_timing(logger=logger, level=_timing_log_level)
def _current_state_bulk(
    connection: Connection, items: set[MarketHistoryID]
) -> dict[int, dict[int, MarketHistoryResponse | None]]:
    """Get the latest stored response for each requested region and type."""
    states_by_region: dict[int, dict[int, MarketHistoryResponse | None]] = {}
    type_ids_by_region: dict[int, set[int]] = {}
    for item in items:
        type_ids_by_region.setdefault(item.region_id, set()).add(item.type_id)

    for region_id, type_ids in type_ids_by_region.items():
        responses_by_type = _reader.read_market_history_responses_by_region(
            connection, region_id=region_id
        )
        states_by_region[region_id] = {}
        for type_id in type_ids:
            responses = responses_by_type.get(type_id, ())
            states_by_region[region_id][type_id] = responses[0] if responses else None
    return states_by_region


def _check_db_status(
    connection: Connection, items: set[MarketHistoryID]
) -> dict[MarketHistoryID, MarketHistoryDBStatus]:
    """Check expiration status in DB."""
    current_states = _current_state_bulk(connection, items)
    now = Instant.now()
    statuses: dict[MarketHistoryID, MarketHistoryDBStatus] = {}

    for market_history_id in items:
        latest_response = current_states[market_history_id.region_id].get(
            market_history_id.type_id
        )
        exists = latest_response is not None
        expiration = (
            (latest_response.argus_expires_at or latest_response.expires_at)
            if exists
            else None
        )
        expired = (
            not exists or expiration is None or Instant.parse_iso(expiration) <= now
        )
        statuses[market_history_id] = MarketHistoryDBStatus(
            market_history_id=market_history_id,
            exists=exists,
            expired=expired,
            current_state=latest_response,
        )

    return statuses


async def update_histories(
    esi_link: EsiLink,
    esi_schema: EsiSchema,
    connection: Connection,
    items: set[MarketHistoryID],
) -> dict[MarketHistoryID, MarketHistoryUpdateResult]:
    """Update database for expired market histories.

    Args:
        esi_link: The ESI link instance.
        esi_schema: The ESI schema.
        connection: Market history database connection.
        items: Set of MarketHistoryID to check and update.

    Returns:
        Dict of MarketHistoryID to MarketHistoryUpdateStatus for all items.
    """
    db_status = _check_db_status(connection, items)
    update_statuses: dict[MarketHistoryID, MarketHistoryUpdateResult] = {}
    items_to_update: set[MarketHistoryID] = set()

    for market_history_id in items:
        status = db_status.get(market_history_id)
        if status is not None and status.exists and not status.expired:
            update_statuses[market_history_id] = MarketHistoryUpdateResult(
                market_history_id=market_history_id,
                update_successful=True,
                update_not_required=True,
                failure_message="",
                previous_state=status.current_state,
                new_state=None,
            )
        else:
            items_to_update.add(market_history_id)
    try:
        async with asyncio.TaskGroup() as task_group:
            update_tasks = {
                market_history_id: task_group.create_task(
                    _fetch_and_update_history(
                        esi_link,
                        esi_schema,
                        connection,
                        market_history_id,
                        current_state=db_status[market_history_id].current_state,
                    )
                )
                for market_history_id in items_to_update
            }
        update_statuses.update({
            market_history_id: task.result()
            for market_history_id, task in update_tasks.items()
        })
    except* Exception as e:
        # TODO Probably need a more robust handling of errors and error types here.
        logger.error("Market History update failed: %s", e)

    return update_statuses
