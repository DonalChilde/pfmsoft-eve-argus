"""Query helpers for the market history database."""

from sqlite3 import Connection

from pfmsoft.eve_argus.helpers.currency import to_cents
from pfmsoft.eve_argus.helpers.package_resource import load_package_resource_text
from pfmsoft.eve_argus.market.history.db import models
from pfmsoft.eve_argus.models.esi import esi_response_models as ERM

_table_def_parent = "pfmsoft.eve_argus.market.orders.db"
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
    ...


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
        start: ISO date string for the most recent date, or None to start at
            the beginning of available history.
        end: ISO date string for the oldest date, or None to continue through
            the end of available history.

    Returns:
        Market history records ordered by date descending, most recent first.
    """
    ...


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
