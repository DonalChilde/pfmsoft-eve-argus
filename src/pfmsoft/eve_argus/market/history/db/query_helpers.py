"""Query helpers for the market history database."""

import sqlite3

from pfmsoft.eve_argus.helpers.currency import to_cents
from pfmsoft.eve_argus.helpers.package_resource import load_package_resouce_text
from pfmsoft.eve_argus.models.esi.esi_response_models import (
    GetMarketsRegionIdHistoryDetail,
)

_table_def_parent = "pfmsoft.eve_argus.market.orders.db"
_table_def_file = "table_definitions.sql"


def load_table_definitions() -> str:
    """Load the SQL table definitions for the market orders database."""
    return load_package_resouce_text(_table_def_parent, _table_def_file)


def write_market_history(
    connection: sqlite3.Connection,
    region_id: int,
    type_id: int,
    data: list[GetMarketsRegionIdHistoryDetail],
):
    """Write market history data to the database."""
    if not data:
        return

    with connection:
        connection.executemany(
            """
            INSERT INTO market_history (region_id, type_id, average,date_,highest,lowest,order_count,volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    region_id,
                    type_id,
                    to_cents(detail.average),
                    detail.date,
                    to_cents(detail.highest),
                    to_cents(detail.lowest),
                    detail.order_count,
                    detail.volume,
                )
                for detail in data
            ],
        )


def get_market_history(
    connection: sqlite3.Connection, region_id: int, type_id: int
) -> list[GetMarketsRegionIdHistoryDetail]: ...
