"""Helper functions for writing data to the database.

Write functions that insert primary records from a response need to:
- write to the response_metadata table first, and get the returned ID.
- use the returned id and possibly other metadata to write to the specific operation_id table.
- use the returned id to write to the specific record table.
"""

# The definition for this database lives at src/pfmsoft/eve_argus/dynamic/db/table_definitions.sql
import logging
from dataclasses import astuple, dataclass
from sqlite3 import Connection
from typing import Any, cast

from pfmsoft.eve_argus.helpers.currency import (
    to_cents,
    to_four_places,
)
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


@log_timing(logger=logger, level=_timing_log_level)
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


@log_timing(logger=logger, level=_timing_log_level)
def write_market_orders(
    connection: Connection,
    market_orders: ERM.GetMarketsRegionIdOrders,
) -> None:
    """Write the market orders to the database."""
    with connection:
        response_metadata_id = write_response_metadata(
            connection,
            received_at=market_orders.received_at,
            expires_at=market_orders.expires_at,
            argus_expires_at=None,
        )
        region_id = market_orders.region_id
        # update the get_markets_region_id_orders_response table
        connection.execute(
            """
            INSERT INTO get_markets_region_id_orders_response (
                response_metadata_id, region_id
            )
            VALUES (?, ?)
            """,
            (response_metadata_id, region_id),
        )
        connection.executemany(
            """
            INSERT INTO market_orders (
                response_metadata_id, region_id, duration, is_buy_order, issued,
                location_id, min_volume, order_id, price, range_, system_id,
                type_id, volume_remain, volume_total
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    response_metadata_id,
                    region_id,
                    order.duration,
                    order.is_buy_order,
                    order.issued,
                    order.location_id,
                    order.min_volume,
                    order.order_id,
                    to_cents(order.price),
                    order.range,
                    order.system_id,
                    order.type_id,
                    order.volume_remain,
                    order.volume_total,
                )
                for order in market_orders.orders
            ),
        )


@log_timing(logger=logger, level=_timing_log_level)
def write_order_summaries(
    connection: Connection,
    order_summaries: Any,
) -> None:
    """Write the order summaries to the database."""
    raise NotImplementedError()


@log_timing(logger=logger, level=_timing_log_level)
def write_system_cost_indices(
    connection: Connection,
    system_cost_indices: ERM.GetIndustrySystems,
) -> None:
    """Write the system cost indices to the database."""
    activity_columns = {
        ERM.CostIndicesActivity.COPYING: "copying",
        ERM.CostIndicesActivity.MANUFACTURING: "manufacturing",
        ERM.CostIndicesActivity.INVENTION: "invention",
        ERM.CostIndicesActivity.REACTION: "reaction",
        ERM.CostIndicesActivity.RESEARCHING_MATERIAL_EFFICIENCY: (
            "researching_material_efficiency"
        ),
        ERM.CostIndicesActivity.RESEARCHING_TIME_EFFICIENCY: (
            "researching_time_efficiency"
        ),
    }

    def to_stored_precision(value: float) -> int:
        return to_four_places(value)

    with connection:
        response_metadata_id = write_response_metadata(
            connection,
            received_at=system_cost_indices.received_at,
            expires_at=system_cost_indices.expires_at,
            argus_expires_at=None,
        )
        connection.execute(
            """
            INSERT INTO get_industry_systems_response (response_metadata_id)
            VALUES (?)
            """,
            (response_metadata_id,),
        )

        @dataclass(slots=True)
        class SystemCostIndexRow:
            system_id: int
            copying: int | None
            manufacturing: int | None
            invention: int | None
            reaction: int | None
            researching_material_efficiency: int | None
            researching_time_efficiency: int | None
            response_metadata_id: int

        rows: list[SystemCostIndexRow] = []
        for system in system_cost_indices.industry_systems:
            values: dict[str, int | None] = {
                column: None for column in activity_columns.values()
            }
            for index in system.cost_indices:
                column = activity_columns.get(index.activity)
                if column is None:
                    raise ValueError(
                        f"Unsupported industry cost index activity: {index.activity}"
                    )
                values[column] = to_stored_precision(index.cost_index)

            rows.append(
                SystemCostIndexRow(
                    system_id=system.solar_system_id,
                    copying=values["copying"],
                    manufacturing=values["manufacturing"],
                    invention=values["invention"],
                    reaction=values["reaction"],
                    researching_material_efficiency=values[
                        "researching_material_efficiency"
                    ],
                    researching_time_efficiency=values["researching_time_efficiency"],
                    response_metadata_id=response_metadata_id,
                )
            )

        connection.executemany(
            """
            INSERT INTO system_cost_indices (
                system_id, copying, manufacturing, invention, reaction,
                researching_material_efficiency, researching_time_efficiency,
                response_metadata_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (astuple(row) for row in rows),
        )


@log_timing(logger=logger, level=_timing_log_level)
def write_corporation_industry_jobs(
    connection: Connection, jobs: ERM.GetCorporationsCorporationIdIndustryJobs
):
    """Write corporation industry jobs to the database."""
    ...


@log_timing(logger=logger, level=_timing_log_level)
def write_corporation_blueprints(
    connection: Connection, blueprints: ERM.GetCorporationsCorporationIdBlueprints
):
    """Write corporation blueprints to the database."""
    ...
