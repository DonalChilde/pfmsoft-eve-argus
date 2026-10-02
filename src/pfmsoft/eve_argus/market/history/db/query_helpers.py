"""Query helpers for the market history database."""

from sqlite3 import Connection

from pfmsoft.eve_argus.helpers.currency import from_cents, to_cents
from pfmsoft.eve_argus.helpers.package_resource import load_package_resource_text
from pfmsoft.eve_argus.market.history.db import models
from pfmsoft.eve_argus.models.esi import esi_response_models as ERM

_table_def_parent = "pfmsoft.eve_argus.market.history.db"
_table_def_file = "table_definitions.sql"


def load_table_definitions() -> str:
    """Load the SQL table definitions for the market orders database."""
    return load_package_resource_text(_table_def_parent, _table_def_file)


def write_market_history(
    connection: Connection,
    data: ERM.GetMarketsRegionIdHistory,
):
    """Write market history data to the database."""
    with connection:
        # Insert each history detail into the database
        connection.executemany(
            """
            INSERT INTO market_history (received_at, region_id, type_id, average,date_,highest,lowest,order_count,volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    data.received_at,
                    data.region_id,
                    data.type_id,
                    to_cents(detail.average),
                    detail.date,
                    to_cents(detail.highest),
                    to_cents(detail.lowest),
                    detail.order_count,
                    detail.volume,
                )
                for detail in data.history
            ],
        )
        # insert market_history_response
        connection.execute(
            """
            INSERT INTO market_history_response (received_at,expires_at, region_id, type_id)
            VALUES (?, ?, ?, ?)
            """,
            (data.received_at, data.expires_at, data.region_id, data.type_id),
        )


def read_market_history(
    connection: Connection,
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
            SELECT received_at, region_id, type_id, average, date_, highest,
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
                region_id=row[1],
                type_id=row[2],
                average=from_cents(row[3]),
                date=row[4],
                highest=from_cents(row[5]),
                lowest=from_cents(row[6]),
                order_count=row[7],
                volume=row[8],
            )
            for row in cursor
        )


def read_market_history_date_range(
    connection: Connection,
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
        SELECT received_at, region_id, type_id, average, date_, highest,
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
                region_id=row[1],
                type_id=row[2],
                average=from_cents(row[3]),
                date=row[4],
                highest=from_cents(row[5]),
                lowest=from_cents(row[6]),
                order_count=row[7],
                volume=row[8],
            )
            for row in cursor
        )


def read_market_history_latest(
    connection: Connection,
    region_id: int,
    type_id: int,
    count: int,
) -> tuple[models.MarketHistoryRecord, ...]:
    """Read the latest market history records.

    Args:
        connection: Database connection.
        region_id: Region ID.
        type_id: Type ID.
        count: Number of records to fetch.

    Returns:
        Latest market history records ordered by date descending.
    """
    ...


def read_market_history_responses(
    connection: Connection, region_id: int, type_id: int
) -> tuple[models.MarketHistoryResponse, ...]: ...
