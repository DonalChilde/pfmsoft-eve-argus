"""Read market history data from the database."""

import logging
from sqlite3 import Connection

from pfmsoft.eve_argus.helpers.currency import from_cents
from pfmsoft.eve_argus.helpers.timing import log_timing
from pfmsoft.eve_argus.market_history import models

logger = logging.getLogger(__name__)

_timing_log_level = logging.INFO


@log_timing(logger=logger, level=_timing_log_level)
def market_history_date_range(
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
def market_history(
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
def market_history_by_region(
    connection: Connection,
    *,
    region_id: int,
    start: str | None = None,
    count: int | None = None,
) -> dict[int, tuple[models.MarketHistoryRecord, ...]]:
    """Read market history records for a specific region.

    Args:
        connection: Database connection.
        region_id: Region ID.
        start: Inclusive ISO date bound for the most recent date, or None to
            start at the beginning of available history.
        count: Positive maximum number of records per type, or None for no limit.

    Returns:
        Dictionary mapping type IDs to tuples of market history records ordered
        by date descending, most recent first.

    Raises:
        ValueError: If count is zero or negative.
    """
    if count is not None and count <= 0:
        raise ValueError("count must be positive")

    query = """
        SELECT received_at, expires_at, argus_expires_at, region_id, type_id,
            average, date_, highest, lowest, order_count, volume
        FROM market_history
        WHERE region_id = ?
    """
    parameters: list[int | str] = [region_id]
    if start is not None:
        query += " AND date_ <= ?"
        parameters.append(start)
    if count is not None:
        query = f"""
            WITH ranked_history AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY type_id ORDER BY date_ DESC
                ) AS history_rank
                FROM ({query})
            )
            SELECT received_at, expires_at, argus_expires_at, region_id, type_id,
                average, date_, highest, lowest, order_count, volume
            FROM ranked_history
            WHERE history_rank <= ?
        """
        parameters.append(count)
    query += " ORDER BY type_id, date_ DESC"

    records_by_type: dict[int, list[models.MarketHistoryRecord]] = {}
    with connection:
        cursor = connection.execute(query, tuple(parameters))
        for row in cursor:
            record = models.MarketHistoryRecord(
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
            records_by_type.setdefault(record.type_id, []).append(record)

    return {type_id: tuple(records) for type_id, records in records_by_type.items()}


@log_timing(logger=logger, level=_timing_log_level)
def market_history_responses(
    connection: Connection, *, region_id: int, type_id: int, count: int | None = None
) -> tuple[models.MarketHistoryResponse, ...]:
    """Read response metadata for a region and type, newest first.

    Sorted by received time descending.

    Args:
        connection: Database connection.
        region_id: Region ID for the market history.
        type_id: Type ID for the market history.
        count: Positive maximum number of responses to read, or None for all
            available.

    Returns:
        Response metadata ordered by received time descending.

    Raises:
        ValueError: If count is zero or negative.
    """
    if count is not None and count <= 0:
        raise ValueError("count must be positive")

    query = """
        SELECT id, received_at, expires_at, argus_expires_at, region_id,
            type_id, response_count
        FROM market_history_response
        WHERE region_id = ? AND type_id = ?
        ORDER BY received_at DESC, id DESC
    """
    parameters = (region_id, type_id)
    if count is not None:
        query += " LIMIT ?"
        parameters = (*parameters, count)

    with connection:
        cursor = connection.execute(query, parameters)
        return tuple(
            models.MarketHistoryResponse(
                response_metadata_id=row[0],
                received_at=row[1],
                expires_at=row[2],
                argus_expires_at=row[3],
                region_id=row[4],
                type_id=row[5],
                response_count=row[6],
            )
            for row in cursor
        )


@log_timing(logger=logger, level=_timing_log_level)
def market_history_responses_by_region(
    connection: Connection, *, region_id: int, count: int | None = None
) -> dict[int, tuple[models.MarketHistoryResponse, ...]]:
    """Read responses for a region, grouped by type.

    Args:
        connection: Database connection.
        region_id: Region ID.
        count: Positive maximum number of responses per type, or None for all
            available.

    Returns:
        Responses grouped by type, ordered newest first within each type.

    Raises:
        ValueError: If count is zero or negative.
    """
    if count is not None and count <= 0:
        raise ValueError("count must be positive")

    query = """
        SELECT id, received_at, expires_at, argus_expires_at, region_id,
            type_id, response_count
        FROM market_history_response
        WHERE region_id = ?
    """
    parameters: tuple[int, ...] = (region_id,)
    if count is not None:
        query = """
            WITH ranked_responses AS (
                SELECT id, received_at, expires_at, argus_expires_at, region_id,
                    type_id, response_count, ROW_NUMBER() OVER (
                        PARTITION BY type_id ORDER BY received_at DESC, id DESC
                    ) AS response_rank
                FROM market_history_response
                WHERE region_id = ?
            )
            SELECT id, received_at, expires_at, argus_expires_at, region_id,
                type_id, response_count
            FROM ranked_responses
            WHERE response_rank <= ?
        """
        parameters = (*parameters, count)
    query += " ORDER BY type_id, received_at DESC, id DESC"

    responses_by_type: dict[int, list[models.MarketHistoryResponse]] = {}
    with connection:
        cursor = connection.execute(query, parameters)
        for row in cursor:
            response = models.MarketHistoryResponse(
                response_metadata_id=row[0],
                received_at=row[1],
                expires_at=row[2],
                argus_expires_at=row[3],
                region_id=row[4],
                type_id=row[5],
                response_count=row[6],
            )
            responses_by_type.setdefault(response.type_id, []).append(response)

    return {
        type_id: tuple(responses) for type_id, responses in responses_by_type.items()
    }
