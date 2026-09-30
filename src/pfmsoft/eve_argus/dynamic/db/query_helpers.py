"""Helper functions for writing data to the database.

Write functions that insert primary records from a response need to:
- write to the response_metadata table first, and get the returned ID.
- use the returned id and possibly other metadata to write to the specific operation_id table.
- use the returned id to write to the specific record table.
"""

# The definition for this database lives at src/pfmsoft/eve_argus/dynamic/db/table_definitions.sql
import logging
from sqlite3 import Connection
from typing import cast

from pfmsoft.eve_argus.helpers.currency import to_cents
from pfmsoft.eve_argus.helpers.timing import log_timing
from pfmsoft.eve_argus.models.esi import esi_response_models as ERM

logger = logging.getLogger(__name__)


_timing_log_level = logging.INFO


@log_timing(logger=logger, level=_timing_log_level)
def write_response_metadata(
    connection: Connection,
    received_at: str,
    expires_at: str | None,
    argus_expires_at: str | None,
) -> int:
    """Write the response metadata to the database.

    Args:
        connection (Connection): The database connection.
        received_at (str): The timestamp when the response was received.
        expires_at (str | None): The timestamp when the response expires.
        argus_expires_at (str | None): The Argus-specific expiration timestamp.

    Returns:
        int: The ID of the inserted row.
    """
    with connection:
        cursor = connection.execute(
            """
            INSERT INTO response_metadata (
                received_at, expires_at, argus_expires_at
            )
            VALUES (?, ?, ?)
            """,
            (received_at, expires_at, argus_expires_at),
        )
        return cast(int, cursor.lastrowid)


def write_universe_prices(
    connection: Connection,
    universe_prices: ERM.GetMarketsPrices,
) -> None:
    """Write the universe prices to the database."""
    with connection:
        response_metadata_id = write_response_metadata(
            connection,
            received_at=universe_prices.received_at,
            expires_at=universe_prices.expires_at,
            argus_expires_at=None,
        )
        # update the get_markets_prices_response table
        connection.execute(
            """
            INSERT INTO get_markets_prices_response (
                response_metadata_id
            )
            VALUES (?)
            """,
            (response_metadata_id,),
        )
        connection.executemany(
            """
            INSERT INTO universe_prices (
                type_id, average_price, adjusted_price, response_metadata_id
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                (
                    price.type_id,
                    to_cents(price.average_price)
                    if price.average_price is not None
                    else None,
                    to_cents(price.adjusted_price)
                    if price.adjusted_price is not None
                    else None,
                    response_metadata_id,
                )
                for price in universe_prices.markets_prices
            ),
        )
