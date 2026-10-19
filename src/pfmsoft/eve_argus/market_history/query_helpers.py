# """Query helpers for the market history database."""

# import logging
# from sqlite3 import Connection

# from pfmsoft.eve_argus.helpers.currency import from_cents, to_cents
# from pfmsoft.eve_argus.helpers.package_resource import load_package_resource_text
# from pfmsoft.eve_argus.helpers.timing import log_timing
# from pfmsoft.eve_argus.market_history import models
# from pfmsoft.eve_argus.models.esi import esi_response_models as ERM

# logger = logging.getLogger(__name__)
# _table_def_parent = "pfmsoft.eve_argus.market.history.db"
# _table_def_file = "table_definitions.sql"
# _timing_log_level = logging.INFO


# def load_table_definitions() -> str:
#     """Load the SQL table definitions for the market orders database."""
#     return load_package_resource_text(_table_def_parent, _table_def_file)


# @log_timing(logger=logger, level=_timing_log_level)
# def write_market_history(
#     connection: Connection,
#     *,
#     history: ERM.GetMarketsRegionIdHistory,
# ) -> None:
#     """Write market history data to the database.

#     Also writes the response metadata.

#     Args:
#         connection: Database connection.
#         history: Market history data.
#     """
#     with connection:
#         # insert market_history_response
#         # This should fail early if the response is already in the DB
#         connection.execute(
#             """
#             INSERT INTO market_history_response (received_at,expires_at, region_id, type_id)
#             VALUES (?, ?, ?, ?)
#             """,
#             (
#                 history.received_at,
#                 history.expires_at,
#                 history.region_id,
#                 history.type_id,
#             ),
#         )
#         # Insert each history detail into the database
#         connection.executemany(
#             """
#             INSERT INTO market_history (received_at, region_id, type_id, average,date_,highest,lowest,order_count,volume)
#             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
#             """,
#             [
#                 (
#                     history.received_at,
#                     history.region_id,
#                     history.type_id,
#                     to_cents(detail.average),
#                     detail.date,
#                     to_cents(detail.highest),
#                     to_cents(detail.lowest),
#                     detail.order_count,
#                     detail.volume,
#                 )
#                 for detail in history.history
#             ],
#         )


