"""Write market history data to the database."""

import logging
from sqlite3 import Connection

from pfmsoft.eve_argus.esi import models as EsiModels
from pfmsoft.eve_argus.helpers.currency import to_cents
from pfmsoft.eve_argus.helpers.timing import log_timing

logger = logging.getLogger(__name__)

_timing_log_level = logging.INFO


@log_timing(logger=logger, level=_timing_log_level)
def write_market_history(
    connection: Connection,
    *,
    history: EsiModels.GetMarketsRegionIdHistory,
) -> None:
    """Write market history data to the database.

    Also writes the response metadata.

    Args:
        connection: Database connection.
        history: Market history data.
    """
    with connection:
        # insert market_history_response
        # This should fail early if the response is already in the DB
        connection.execute(
            """
            INSERT INTO market_history_response (received_at,expires_at,argus_expires_at, region_id, type_id, response_count)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                history.received_at,
                history.expires_at,
                history.expires_at,
                history.region_id,
                history.type_id,
                len(history.history),
            ),
        )
        # Insert each history detail into the database
        connection.executemany(
            """
            INSERT INTO market_history (received_at, expires_at, argus_expires_at, region_id, type_id, average,date_,highest,lowest,order_count,volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    history.received_at,
                    history.expires_at,
                    history.expires_at,
                    history.region_id,
                    history.type_id,
                    to_cents(detail.average),
                    detail.date,
                    to_cents(detail.highest),
                    to_cents(detail.lowest),
                    detail.order_count,
                    detail.volume,
                )
                for detail in history.history
            ],
        )
