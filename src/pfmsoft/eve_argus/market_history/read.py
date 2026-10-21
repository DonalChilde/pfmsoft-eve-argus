"""Read market history data from the database."""

import logging
from sqlite3 import Connection

from pfmsoft.eve_argus.helpers.currency import from_cents
from pfmsoft.eve_argus.helpers.timing import log_timing
from pfmsoft.eve_argus.market_history import models

logger = logging.getLogger(__name__)

_timing_log_level = logging.INFO


@log_timing(logger=logger, level=_timing_log_level)
def read_market_history(
    connection: Connection,
    *,
    region_id: int,
    type_id: int,
) -> tuple[models.MarketHistoryRecord, ...]:
    """Read all market history for a region and type.

    Args:
        connection: Database connection.
        region_id: Region ID.
        type_id: Type ID.

    Returns:
        Market history records ordered by date descending.
    """
    with connection:
        cursor = connection.execute(
            """
            SELECT received_at,expires_at, argus_expires_at, region_id, type_id, average, date_, highest,
                lowest, order_count, volume
            FROM market_history
            WHERE region_id = ? AND type_id = ?
            ORDER BY date_ DESC
            """,
            (region_id, type_id),
        )
        return tuple(
            models.MarketHistoryRecord(
                received_at=row[0],
                expires_at=row[1],
                argus_expires_at=row[2],
                region_id=row[3],
                type_id=row[4],
                average=from_cents(row[5]),
                date=row[6],
                highest=from_cents(row[7]),
                lowest=from_cents(row[8]),
                order_count=row[9],
                volume=row[10],
            )
            for row in cursor
        )


@log_timing(logger=logger, level=_timing_log_level)
def read_market_history_date_range(
    connection: Connection,
    *,
    region_id: int,
    type_id: int,
    start: str | None,
    end: str | None,
) -> tuple[models.MarketHistoryRecord, ...]:
    """Read market history between date bounds, ordered newest first.

    Args:
        connection: Database connection.
        region_id: Region ID for the market history.
        type_id: Type ID for the market history.
        start: Inclusive ISO date bound for the most recent date, or None to
            start at the beginning of available history.
        end: Inclusive ISO date bound for the oldest date, or None to continue
            through the end of available history.

    Returns:
        Market history records ordered by date descending, most recent first.
    """
    query = """
        SELECT received_at, expires_at, argus_expires_at, region_id, type_id, average, date_, highest,
            lowest, order_count, volume
        FROM market_history
        WHERE region_id = ? AND type_id = ?
    """
    parameters: list[int | str] = [region_id, type_id]
    if start is not None:
        query += " AND date_ <= ?"
        parameters.append(start)
    if end is not None:
        query += " AND date_ >= ?"
        parameters.append(end)
    query += " ORDER BY date_ DESC"

    with connection:
        cursor = connection.execute(query, tuple(parameters))
        return tuple(
            models.MarketHistoryRecord(
                received_at=row[0],
                expires_at=row[1],
                argus_expires_at=row[2],
                region_id=row[3],
                type_id=row[4],
                average=from_cents(row[5]),
                date=row[6],
                highest=from_cents(row[7]),
                lowest=from_cents(row[8]),
                order_count=row[9],
                volume=row[10],
            )
            for row in cursor
        )


@log_timing(logger=logger, level=_timing_log_level)
def read_market_history_date_count(
    connection: Connection,
    *,
    region_id: int,
    type_id: int,
    start: str | None = None,
    count: int | None = None,
) -> tuple[models.MarketHistoryRecord, ...]:
    """Read market history starting at the given date, limited by count.

    Args:
        connection: Database connection.
        region_id: Region ID.
        type_id: Type ID.
        start: Inclusive ISO date bound for the most recent date, or None to
            start at the beginning of available history.
        count: Maximum number of records to count, or None for no limit.

    Returns:
        Market history records ordered by date descending, most recent first.

    Raises:
        ValueError: If count is zero or negative.
    """
    if count is not None and count <= 0:
        raise ValueError("count must be positive")

    query = """
        SELECT received_at,expires_at, argus_expires_at, region_id, type_id, average, date_, highest,
            lowest, order_count, volume
        FROM market_history
        WHERE region_id = ? AND type_id = ?
    """
    parameters: list[int | str] = [region_id, type_id]
    if start is not None:
        query += " AND date_ <= ?"
        parameters.append(start)
    query += " ORDER BY date_ DESC"
    if count is not None:
        query += " LIMIT ?"
        parameters.append(count)

    with connection:
        cursor = connection.execute(query, tuple(parameters))
        return tuple(
            models.MarketHistoryRecord(
                received_at=row[0],
                expires_at=row[1],
                argus_expires_at=row[2],
                region_id=row[3],
                type_id=row[4],
                average=from_cents(row[5]),
                date=row[6],
                highest=from_cents(row[7]),
                lowest=from_cents(row[8]),
                order_count=row[9],
                volume=row[10],
            )
            for row in cursor
        )


@log_timing(logger=logger, level=_timing_log_level)
def read_market_history_latest(
    connection: Connection,
    *,
    region_id: int,
    type_id: int,
    count: int,
) -> tuple[models.MarketHistoryRecord, ...]:
    """Read the latest market history records.

    Args:
        connection: Database connection.
        region_id: Region ID.
        type_id: Type ID.
        count: Number of records to fetch. Must be > 0.

    Returns:
        Latest market history records ordered by date descending.

    Raises:
        ValueError: If count is negative or zero.
    """
    if count <= 0:
        raise ValueError("count must be positive")

    with connection:
        cursor = connection.execute(
            """
            SELECT received_at, expires_at, argus_expires_at, region_id, type_id, average, date_, highest,
                lowest, order_count, volume
            FROM market_history
            WHERE region_id = ? AND type_id = ?
            ORDER BY date_ DESC
            LIMIT ?
            """,
            (region_id, type_id, count),
        )
        return tuple(
            models.MarketHistoryRecord(
                received_at=row[0],
                expires_at=row[1],
                argus_expires_at=row[2],
                region_id=row[3],
                type_id=row[4],
                average=from_cents(row[5]),
                date=row[6],
                highest=from_cents(row[7]),
                lowest=from_cents(row[8]),
                order_count=row[9],
                volume=row[10],
            )
            for row in cursor
        )


@log_timing(logger=logger, level=_timing_log_level)
def read_market_history_latest_response(
    connection: Connection, *, region_id: int, type_id: int
) -> models.MarketHistoryResponse | None:
    """Read only the newest response metadata for a region/type pair.

    Returns:
        Latest metadata ordered by received time and then ID descending, or None
        if no response exists for the pair.
    """
    with connection:
        row = connection.execute(
            """
            SELECT id, received_at, expires_at, argus_expires_at, region_id,
                type_id
            FROM market_history_response
            WHERE region_id = ? AND type_id = ?
            ORDER BY received_at DESC, id DESC
            LIMIT 1
            """,
            (region_id, type_id),
        ).fetchone()
        if row is None:
            return None
        return models.MarketHistoryResponse(
            response_metadata_id=row[0],
            received_at=row[1],
            expires_at=row[2],
            argus_expires_at=row[3],
            region_id=row[4],
            type_id=row[5],
        )


@log_timing(logger=logger, level=_timing_log_level)
def market_history_response_exists(
    connection: Connection, *, region_id: int, type_id: int, received_at: str
) -> bool:
    """Check for an exact stored region/type/received-time response."""
    with connection:
        row = connection.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM market_history_response
                WHERE received_at = ? AND region_id = ? AND type_id = ?
            )
            """,
            (received_at, region_id, type_id),
        ).fetchone()
        return bool(row[0])


@log_timing(logger=logger, level=_timing_log_level)
def read_market_history_responses(
    connection: Connection,
    *,
    region_id: int,
    type_id: int,
) -> tuple[models.MarketHistoryResponse, ...]:
    """Read response metadata for a region and type, newest first.

    Args:
        connection: Database connection.
        region_id: Region ID for the market history.
        type_id: Type ID for the market history.

    Returns:
        Response metadata ordered by received time descending.
    """
    with connection:
        cursor = connection.execute(
            """
            SELECT id, received_at, expires_at, argus_expires_at, region_id,
                type_id
            FROM market_history_response
            WHERE region_id = ? AND type_id = ?
            ORDER BY received_at DESC, id DESC
            """,
            (region_id, type_id),
        )
        return tuple(
            models.MarketHistoryResponse(
                response_metadata_id=row[0],
                received_at=row[1],
                expires_at=row[2],
                argus_expires_at=row[3],
                region_id=row[4],
                type_id=row[5],
            )
            for row in cursor
        )


@log_timing(logger=logger, level=_timing_log_level)
def read_market_history_responses_by_region(
    connection: Connection, *, region_id: int
) -> dict[int, tuple[models.MarketHistoryResponse, ...]]:
    """Read responses for a region, grouped by type.

    Args:
        connection: Database connection.
        region_id: Region ID.

    Returns:
        Responses grouped by type.
    """
    responses_by_type: dict[int, list[models.MarketHistoryResponse]] = {}
    with connection:
        cursor = connection.execute(
            """
            SELECT id, received_at, expires_at, argus_expires_at, region_id,
                type_id
            FROM market_history_response
            WHERE region_id = ?
            ORDER BY type_id, received_at DESC, id DESC
            """,
            (region_id,),
        )
        for row in cursor:
            response = models.MarketHistoryResponse(
                response_metadata_id=row[0],
                received_at=row[1],
                expires_at=row[2],
                argus_expires_at=row[3],
                region_id=row[4],
                type_id=row[5],
            )
            responses_by_type.setdefault(response.type_id, []).append(response)

    return {
        type_id: tuple(responses) for type_id, responses in responses_by_type.items()
    }
