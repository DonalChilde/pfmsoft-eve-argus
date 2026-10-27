"""Write dynamic data to the database."""

import logging
from dataclasses import astuple, dataclass
from sqlite3 import Connection
from typing import cast
from warnings import deprecated

from pfmsoft.eve_argus.dynamic import models
from pfmsoft.eve_argus.esi import models as EsiModels
from pfmsoft.eve_argus.helpers.currency import (
    to_cents,
    to_four_places,
)
from pfmsoft.eve_argus.helpers.timing import log_timing

logger = logging.getLogger(__name__)


_timing_log_level = logging.INFO


@log_timing(logger=logger, level=_timing_log_level)
def response_metadata(
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
def markets_prices(
    connection: Connection,
    markets_prices: EsiModels.GetMarketsPrices,
) -> None:
    """Write the universe markets prices to the database."""
    with connection:
        response_metadata_id = response_metadata(
            connection,
            received_at=markets_prices.received_at,
            expires_at=markets_prices.expires_at,
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
            INSERT INTO markets_prices (
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
                for price in markets_prices.markets_prices
            ),
        )


@log_timing(logger=logger, level=_timing_log_level)
def market_orders(
    connection: Connection,
    market_orders: EsiModels.GetMarketsRegionIdOrders,
) -> None:
    """Write the market orders to the database."""
    with connection:
        response_metadata_id = response_metadata(
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
                response_metadata_id, region_id, received_at
            )
            VALUES (?, ?, ?)
            """,
            (response_metadata_id, region_id, market_orders.received_at),
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


@deprecated("Prefer on demand calculations.")
@log_timing(logger=logger, level=_timing_log_level)
def order_summaries(
    connection: Connection,
    order_summaries: models.OrderSummaryDataset,
) -> int:
    """Save a scoped summary for an existing market-order response.

    Returns:
        The stable ID of the saved summary response.

    Raises:
        ValueError: If the source response or any summary scope/type is inconsistent.
    """
    if (
        order_summaries.system_id is not None
        and order_summaries.location_id is not None
    ):
        raise ValueError("Cannot specify both system_id and location_id.")

    source = connection.execute(
        """
        SELECT response.region_id, metadata.received_at, metadata.expires_at,
               metadata.argus_expires_at
        FROM get_markets_region_id_orders_response AS response
        JOIN response_metadata AS metadata
            ON metadata.id = response.response_metadata_id
        WHERE response.response_metadata_id = ?
        """,
        (order_summaries.response_metadata_id,),
    ).fetchone()
    if source is None:
        raise ValueError("No market orders response found for the summary source.")
    if tuple(source) != (
        order_summaries.region_id,
        order_summaries.received_at,
        order_summaries.expires_at,
        order_summaries.argus_expires_at,
    ):
        raise ValueError("Summary metadata does not match the source market orders.")

    for type_id, summary in order_summaries.records.items():
        for is_buy_summary, record in (
            (True, summary.buy_summary),
            (False, summary.sell_summary),
        ):
            if record is not None and (
                record.region_id != order_summaries.region_id
                or record.type_id != type_id
                or record.system_id != order_summaries.system_id
                or record.location_id != order_summaries.location_id
                or record.is_buy_summary != is_buy_summary
            ):
                raise ValueError("Summary record does not match its dataset or side.")

    with connection:
        existing = connection.execute(
            """
            SELECT id FROM order_summary_response
            WHERE response_metadata_id = ? AND region_id = ?
              AND system_id IS ? AND location_id IS ?
            """,
            (
                order_summaries.response_metadata_id,
                order_summaries.region_id,
                order_summaries.system_id,
                order_summaries.location_id,
            ),
        ).fetchone()
        if existing is None:
            cursor = connection.execute(
                """
                INSERT INTO order_summary_response (
                    response_metadata_id, region_id, system_id, location_id
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    order_summaries.response_metadata_id,
                    order_summaries.region_id,
                    order_summaries.system_id,
                    order_summaries.location_id,
                ),
            )
            batch_id = cast(int, cursor.lastrowid)
        else:
            batch_id = existing[0]
            connection.execute(
                "DELETE FROM order_summaries WHERE order_summary_response_id = ?",
                (batch_id,),
            )
            connection.execute(
                "DELETE FROM order_summary_types WHERE order_summary_response_id = ?",
                (batch_id,),
            )

        connection.executemany(
            """
            INSERT INTO order_summary_types (order_summary_response_id, type_id)
            VALUES (?, ?)
            """,
            ((batch_id, type_id) for type_id in order_summaries.records),
        )
        connection.executemany(
            """
            INSERT INTO order_summaries (
                order_summary_response_id, region_id, type_id, system_id,
                location_id, is_buy_summary, five_price, five_orders, five_items,
                lowest, highest, average, total_items, total_orders,
                filtered_items, filtered_orders
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    batch_id,
                    record.region_id,
                    record.type_id,
                    record.system_id,
                    record.location_id,
                    int(record.is_buy_summary),
                    to_cents(record.five_price),
                    record.five_orders,
                    record.five_items,
                    to_cents(record.lowest),
                    to_cents(record.highest),
                    to_cents(record.average),
                    record.total_items,
                    record.total_orders,
                    record.filtered_items,
                    record.filtered_orders,
                )
                for record in order_summaries.iter_summaries()
            ),
        )
    return batch_id


@log_timing(logger=logger, level=_timing_log_level)
def system_cost_indices(
    connection: Connection,
    system_cost_indices: EsiModels.GetIndustrySystems,
) -> None:
    """Write the system cost indices to the database."""
    activity_columns = {
        EsiModels.CostIndicesActivity.COPYING: "copying",
        EsiModels.CostIndicesActivity.MANUFACTURING: "manufacturing",
        EsiModels.CostIndicesActivity.INVENTION: "invention",
        EsiModels.CostIndicesActivity.REACTION: "reaction",
        EsiModels.CostIndicesActivity.RESEARCHING_MATERIAL_EFFICIENCY: (
            "researching_material_efficiency"
        ),
        EsiModels.CostIndicesActivity.RESEARCHING_TIME_EFFICIENCY: (
            "researching_time_efficiency"
        ),
    }

    def to_stored_precision(value: float) -> int:
        return to_four_places(value)

    with connection:
        response_metadata_id = response_metadata(
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
def corporation_industry_jobs(
    connection: Connection, jobs: EsiModels.GetCorporationsCorporationIdIndustryJobs
) -> None:
    """Write corporation industry jobs to the database."""

    @dataclass(slots=True)
    class CorporationIndustryJobRow:
        corporation_id: int
        activity_id: int
        blueprint_id: int
        blueprint_location_id: int
        blueprint_type_id: int
        completed_character_id: int | None
        completed_date: str | None
        cost: int | None
        duration: int
        end_date: str
        facility_id: int
        installer_id: int
        job_id: int
        licensed_runs: int | None
        location_id: int
        output_location_id: int
        pause_date: str | None
        probability: float | None
        product_type_id: int | None
        runs: int
        start_date: str
        status: str
        successful_runs: int | None
        response_metadata_id: int

    with connection:
        response_metadata_id = response_metadata(
            connection,
            received_at=jobs.received_at,
            expires_at=jobs.expires_at,
            argus_expires_at=None,
        )
        connection.execute(
            """
            INSERT INTO get_corporations_corporation_id_industry_jobs_response (
                response_metadata_id, corporation_id
            )
            VALUES (?, ?)
            """,
            (response_metadata_id, jobs.corporation_id),
        )

        rows = [
            CorporationIndustryJobRow(
                corporation_id=jobs.corporation_id,
                activity_id=job.activity_id,
                blueprint_id=job.blueprint_id,
                blueprint_location_id=job.blueprint_location_id,
                blueprint_type_id=job.blueprint_type_id,
                completed_character_id=job.completed_character_id,
                completed_date=job.completed_date,
                cost=to_cents(job.cost) if job.cost is not None else None,
                duration=job.duration,
                end_date=job.end_date,
                facility_id=job.facility_id,
                installer_id=job.installer_id,
                job_id=job.job_id,
                licensed_runs=job.licensed_runs,
                location_id=job.location_id,
                output_location_id=job.output_location_id,
                pause_date=job.pause_date,
                probability=job.probability,
                product_type_id=job.product_type_id,
                runs=job.runs,
                start_date=job.start_date,
                status=job.status.value,
                successful_runs=job.successful_runs,
                response_metadata_id=response_metadata_id,
            )
            for job in jobs.industry_jobs
        ]
        connection.executemany(
            """
            INSERT INTO corporation_industry_jobs (
                corporation_id, activity_id, blueprint_id, blueprint_location_id,
                blueprint_type_id, completed_character_id, completed_date, cost,
                duration, end_date, facility_id, installer_id, job_id,
                licensed_runs, location_id, output_location_id, pause_date,
                probability, product_type_id, runs, start_date, status,
                successful_runs, response_metadata_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (astuple(row) for row in rows),
        )


@log_timing(logger=logger, level=_timing_log_level)
def corporation_blueprints(
    connection: Connection, blueprints: EsiModels.GetCorporationsCorporationIdBlueprints
) -> None:
    """Write corporation blueprints to the database."""

    @dataclass(slots=True)
    class CorporationBlueprintRow:
        corporation_id: int
        item_id: int
        type_id: int
        location_id: int
        location_flag: str
        quantity: int
        time_efficiency: int
        material_efficiency: int
        runs: int
        response_metadata_id: int

    with connection:
        response_metadata_id = response_metadata(
            connection,
            received_at=blueprints.received_at,
            expires_at=blueprints.expires_at,
            argus_expires_at=None,
        )
        connection.execute(
            """
            INSERT INTO get_corporations_corporation_id_blueprints_response (
                response_metadata_id, corporation_id
            )
            VALUES (?, ?)
            """,
            (response_metadata_id, blueprints.corporation_id),
        )

        rows = [
            CorporationBlueprintRow(
                corporation_id=blueprints.corporation_id,
                item_id=blueprint.item_id,
                type_id=blueprint.type_id,
                location_id=blueprint.location_id,
                location_flag=blueprint.location_flag.value,
                quantity=blueprint.quantity,
                time_efficiency=blueprint.time_efficiency,
                material_efficiency=blueprint.material_efficiency,
                runs=blueprint.runs,
                response_metadata_id=response_metadata_id,
            )
            for blueprint in blueprints.blueprints
        ]
        connection.executemany(
            """
            INSERT INTO corporation_blueprints (
                corporation_id, item_id, type_id, location_id, location_flag,
                quantity, time_efficiency, material_efficiency, runs,
                response_metadata_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (astuple(row) for row in rows),
        )
