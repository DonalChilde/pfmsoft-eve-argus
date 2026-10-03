"""Update market history data for items."""

from dataclasses import dataclass
from sqlite3 import Connection

from pfmsoft.eve_link import (
    EsiLink,
    EsiRequest,
    EsiRequestGroup,
    EsiResponse,
    EsiSchema,
    FailedEsiResponse,
)

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
class UpdateStatus:
    """Status of an update."""

    # placeholder dataclass, fields to be updated as flow develops
    market_history_id: MarketHistoryID
    update_successful: bool
    db_was_current: bool
    failure_message: str


@dataclass(slots=True, kw_only=True, frozen=True)
class MarketHistoryStatus:
    """Database status for market history."""

    market_history_id: MarketHistoryID
    expired: bool


async def _update_history(
    esi_link: EsiLink,
    esi_schema: EsiSchema,
    connection: Connection,
    market_history_id: MarketHistoryID,
) -> UpdateStatus:
    """Update market history for an item.

    Checks if history is expired and updates it.

    This function does not check to see if the current database data is eligible for update.
    It only makes the request andupdates the data.

    Args:
        esi_link: The ESI link instance.
        esi_schema: The ESI schema.
        connection: Market history database connection.
        market_history_id: MarketHistoryID.

    Returns:
        UpdateStatus indicating success or failure.
    """
    ...


def _check_db_status(
    connection: Connection, items: set[MarketHistoryID]
) -> set[MarketHistoryStatus]:
    """Check expiration status in DB."""
    # collect unique region ids
    # get response records for those regions
    # check each item against the response
    # return set of MarketHistoryStatus
    ...


async def update_histories(
    esi_link: EsiLink,
    esi_schema: EsiSchema,
    connection: Connection,
    items: set[MarketHistoryID],
) -> list[UpdateStatus]:
    """Update expired market histories.

    Args:
        esi_link: The ESI link instance.
        esi_schema: The ESI schema.
        connection: Market history database connection.
        items: Set of MarketHistoryID to check and update.

    Returns:
        List of UpdateStatus for all items.
    """
    # check db status first
    db_status = _check_db_status(connection, items)
    # collect expired items
    expired_items = {s.market_history_id for s in db_status if s.expired}
    # only update expired items
    # use task group here? Prefer newer python language features and idioms.

    # return the update status for all items.
