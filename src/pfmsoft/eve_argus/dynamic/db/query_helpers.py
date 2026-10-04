"""Helper functions for writing to and reading from the database.

Write functions that insert primary records from a response need to:
- write to the response_metadata table first, and get the returned ID.
- use the returned id and possibly other metadata to write to the specific operation_id table.
- use the returned id to write to the specific record table.
"""

# Pending naming cleanup: rename get_ functions to read_.
# All *_responses readers return newest received_at first; IDs break timestamp ties.
# The definition for this database lives at src/pfmsoft/eve_argus/dynamic/db/table_definitions.sql
import logging
from dataclasses import astuple, dataclass
from sqlite3 import Connection
from typing import cast

from pfmsoft.eve_argus.dynamic.db import models
from pfmsoft.eve_argus.helpers.currency import (
    from_cents,
    from_four_places,
    to_cents,
    to_four_places,
)
from pfmsoft.eve_argus.helpers.package_resource import load_package_resource_text
from pfmsoft.eve_argus.helpers.timing import log_timing
from pfmsoft.eve_argus.models.esi import esi_response_models as ERM

logger = logging.getLogger(__name__)

_table_def_parent = "pfmsoft.eve_argus.dynamic.db"
_table_def_file = "table_definitions.sql"
_timing_log_level = logging.INFO


def load_table_definitions() -> str:
    """Load the SQL table definitions for the dynamic database."""
    return load_package_resource_text(_table_def_parent, _table_def_file)


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
def write_markets_prices(
    connection: Connection,
    markets_prices: ERM.GetMarketsPrices,
) -> None:
    """Write the universe markets prices to the database."""
    with connection:
        response_metadata_id = write_response_metadata(
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


@log_timing(logger=logger, level=_timing_log_level)
def write_order_summaries(
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
def get_order_summaries(
    connection: Connection, order_summary_response_id: int
) -> models.OrderSummaryDataset:
    """Retrieve a scoped summary dataset by its saved response ID.

    Raises:
        ValueError: If the summary response does not exist.
    """
    metadata = connection.execute(
        """
        SELECT response.response_metadata_id, metadata.received_at,
               metadata.expires_at, metadata.argus_expires_at, response.region_id,
               response.system_id, response.location_id
        FROM order_summary_response AS response
        JOIN response_metadata AS metadata
            ON metadata.id = response.response_metadata_id
        WHERE response.id = ?
        """,
        (order_summary_response_id,),
    ).fetchone()
    if metadata is None:
        raise ValueError(
            f"No order summary response found for ID {order_summary_response_id}"
        )

    grouped: dict[int, dict[bool, models.OrderSummaryRecord]] = {
        row[0]: {}
        for row in connection.execute(
            """
            SELECT type_id FROM order_summary_types
            WHERE order_summary_response_id = ? ORDER BY type_id
            """,
            (order_summary_response_id,),
        )
    }
    for row in connection.execute(
        """
        SELECT type_id, region_id, system_id, location_id, is_buy_summary,
               five_price, five_orders, five_items, lowest, highest, average,
               total_items, total_orders, filtered_items, filtered_orders
        FROM order_summaries WHERE order_summary_response_id = ?
        ORDER BY type_id, is_buy_summary DESC
        """,
        (order_summary_response_id,),
    ):
        grouped[row[0]][bool(row[4])] = models.OrderSummaryRecord(
            type_id=row[0],
            region_id=row[1],
            system_id=row[2],
            location_id=row[3],
            is_buy_summary=bool(row[4]),
            five_price=from_cents(row[5]),
            five_orders=row[6],
            five_items=row[7],
            lowest=from_cents(row[8]),
            highest=from_cents(row[9]),
            average=from_cents(row[10]),
            total_items=row[11],
            total_orders=row[12],
            filtered_items=row[13],
            filtered_orders=row[14],
        )

    return models.OrderSummaryDataset(
        response_metadata_id=metadata[0],
        received_at=metadata[1],
        expires_at=metadata[2],
        argus_expires_at=metadata[3],
        region_id=metadata[4],
        system_id=metadata[5],
        location_id=metadata[6],
        records={
            type_id: models.BuySellSummary(
                buy_summary=sides.get(True), sell_summary=sides.get(False)
            )
            for type_id, sides in grouped.items()
        },
    )


@log_timing(logger=logger, level=_timing_log_level)
def get_order_summary_responses(
    connection: Connection, region_id: int | None = None
) -> list[models.OrderSummaryResponse]:
    """List saved summary scopes, optionally filtered by region ID."""
    query = """
        SELECT response.id, response.response_metadata_id, metadata.received_at,
               metadata.expires_at, metadata.argus_expires_at, response.region_id,
               response.system_id, response.location_id
        FROM order_summary_response AS response
        JOIN response_metadata AS metadata
            ON metadata.id = response.response_metadata_id
    """
    parameters: tuple[int, ...] = ()
    if region_id is not None:
        query += " WHERE response.region_id = ?"
        parameters = (region_id,)
    query += " ORDER BY metadata.received_at DESC, response.id DESC"

    return [
        models.OrderSummaryResponse(
            order_summary_response_id=row[0],
            response_metadata_id=row[1],
            received_at=row[2],
            expires_at=row[3],
            argus_expires_at=row[4],
            region_id=row[5],
            system_id=row[6],
            location_id=row[7],
        )
        for row in connection.execute(query, parameters)
    ]


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
        response_metadata_id = write_response_metadata(
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
def write_corporation_blueprints(
    connection: Connection, blueprints: ERM.GetCorporationsCorporationIdBlueprints
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
        response_metadata_id = write_response_metadata(
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


@log_timing(logger=logger, level=_timing_log_level)
def get_response_metadata(
    connection: Connection, response_metadata_ids: set[int] | None
) -> list[models.ResponseMetadata]:
    """Get response metadata by IDs.

    Args:
        connection: sqlite3 db connection.
        response_metadata_ids: IDs to fetch. If None, fetch all.

    Returns:
        List of response metadata.
    """
    query = """
        SELECT id, received_at, expires_at, argus_expires_at
        FROM response_metadata
    """
    parameters: tuple[int, ...] = ()
    if response_metadata_ids is not None:
        if not response_metadata_ids:
            return []
        placeholders = ", ".join("?" for _ in response_metadata_ids)
        query += f" WHERE id IN ({placeholders})"
        parameters = tuple(response_metadata_ids)
    query += " ORDER BY id"

    return [
        models.ResponseMetadata(
            response_metadata_id=row[0],
            received_at=row[1],
            expires_at=row[2],
            argus_expires_at=row[3],
        )
        for row in connection.execute(query, parameters)
    ]


@log_timing(logger=logger, level=_timing_log_level)
def get_markets_prices_responses(
    connection: Connection,
) -> list[models.MarketsPricesResponse]:
    """Get metadata for all stored universe prices responses."""
    return [
        models.MarketsPricesResponse(
            response_metadata_id=row[0],
            received_at=row[1],
            expires_at=row[2],
            argus_expires_at=row[3],
        )
        for row in connection.execute(
            """
            SELECT metadata.id, metadata.received_at, metadata.expires_at,
                   metadata.argus_expires_at
            FROM get_markets_prices_response AS response
            JOIN response_metadata AS metadata
                ON metadata.id = response.response_metadata_id
            ORDER BY metadata.received_at DESC, metadata.id DESC
            """
        )
    ]


@log_timing(logger=logger, level=_timing_log_level)
def get_markets_prices(
    connection: Connection, response_metadata_id: int
) -> models.MarketsPricesDataset:
    """Get a universe markets prices dataset by response metadata ID.

    Args:
        connection: SQLite database connection.
        response_metadata_id: ID identifying the stored universe prices response.

    Returns:
        The response metadata and universe price records indexed by type ID.

    Raises:
        ValueError: If the ID does not identify a stored universe prices response.
    """
    metadata = connection.execute(
        """
        SELECT metadata.id, metadata.received_at, metadata.expires_at,
               metadata.argus_expires_at
        FROM get_markets_prices_response AS response
        JOIN response_metadata AS metadata
            ON metadata.id = response.response_metadata_id
        WHERE metadata.id = ?
        """,
        (response_metadata_id,),
    ).fetchone()
    if metadata is None:
        raise ValueError(
            "No universe markets prices response found for response metadata ID "
            f"{response_metadata_id}"
        )

    records = {
        row[0]: models.MarketsPriceRecord(
            type_id=row[0],
            average_price=from_cents(row[1]) if row[1] is not None else None,
            adjusted_price=from_cents(row[2]) if row[2] is not None else None,
            response_metadata_id=row[3],
        )
        for row in connection.execute(
            """
            SELECT type_id, average_price, adjusted_price, response_metadata_id
            FROM markets_prices
            WHERE response_metadata_id = ?
            ORDER BY type_id
            """,
            (response_metadata_id,),
        )
    }

    return models.MarketsPricesDataset(
        response_metadata_id=metadata[0],
        received_at=metadata[1],
        expires_at=metadata[2],
        argus_expires_at=metadata[3],
        records=records,
    )


@log_timing(logger=logger, level=_timing_log_level)
def get_market_orders_responses(
    connection: Connection, region_id: int | None
) -> list[models.MarketOrdersResponse]:
    """Get metadata for stored market-order responses, optionally filtered by region."""
    query = """
        SELECT metadata.id, metadata.received_at, metadata.expires_at,
               metadata.argus_expires_at, response.region_id
        FROM get_markets_region_id_orders_response AS response
        JOIN response_metadata AS metadata
            ON metadata.id = response.response_metadata_id
    """
    parameters: list[int] = []
    if region_id is not None:
        query += " WHERE response.region_id = ?"
        parameters.append(region_id)
    query += " ORDER BY metadata.received_at DESC, metadata.id DESC"

    return [
        models.MarketOrdersResponse(
            response_metadata_id=row[0],
            received_at=row[1],
            expires_at=row[2],
            argus_expires_at=row[3],
            region_id=row[4],
        )
        for row in connection.execute(query, parameters)
    ]


@log_timing(logger=logger, level=_timing_log_level)
def get_market_orders(
    connection: Connection, response_metadata_id: int
) -> models.MarketOrdersDataset:
    """Get the market order dataset for a response metadata ID."""
    metadata = connection.execute(
        """
        SELECT metadata.id, metadata.received_at, metadata.expires_at,
               metadata.argus_expires_at, response.region_id
        FROM get_markets_region_id_orders_response AS response
        JOIN response_metadata AS metadata
            ON metadata.id = response.response_metadata_id
        WHERE metadata.id = ?
        """,
        (response_metadata_id,),
    ).fetchone()
    if metadata is None:
        raise ValueError(
            "No market orders response found for response metadata ID "
            f"{response_metadata_id}"
        )

    grouped_orders: dict[int, dict[str, list[models.MarketOrderRecord]]] = {}
    for row in connection.execute(
        """
        SELECT type_id, response_metadata_id, region_id, duration, is_buy_order,
               issued, location_id, min_volume, order_id, price, range_,
               system_id, volume_remain, volume_total
        FROM market_orders
        WHERE response_metadata_id = ?
        ORDER BY type_id, order_id
        """,
        (response_metadata_id,),
    ):
        type_id = row[0]
        bucket = grouped_orders.setdefault(type_id, {"buy": [], "sell": []})
        order = models.MarketOrderRecord(
            response_metadata_id=row[1],
            region_id=row[2],
            duration=row[3],
            is_buy_order=bool(row[4]),
            issued=row[5],
            location_id=row[6],
            min_volume=row[7],
            order_id=row[8],
            price=from_cents(row[9]),
            range=row[10],
            system_id=row[11],
            type_id=type_id,
            volume_remain=row[12],
            volume_total=row[13],
        )
        bucket["buy" if order.is_buy_order else "sell"].append(order)

    records = {
        type_id: models.BuySellOrders(
            buy_orders=tuple(bucket["buy"]),
            sell_orders=tuple(bucket["sell"]),
        )
        for type_id, bucket in grouped_orders.items()
    }

    return models.MarketOrdersDataset(
        response_metadata_id=metadata[0],
        received_at=metadata[1],
        expires_at=metadata[2],
        argus_expires_at=metadata[3],
        region_id=metadata[4],
        records=records,
    )


@log_timing(logger=logger, level=_timing_log_level)
def get_system_cost_indices_responses(
    connection: Connection,
) -> list[models.SystemCostIndicesResponse]:
    """Get metadata for all stored system cost index responses."""
    return [
        models.SystemCostIndicesResponse(
            response_metadata_id=row[0],
            received_at=row[1],
            expires_at=row[2],
            argus_expires_at=row[3],
        )
        for row in connection.execute(
            """
            SELECT metadata.id, metadata.received_at, metadata.expires_at,
                   metadata.argus_expires_at
            FROM get_industry_systems_response AS response
            JOIN response_metadata AS metadata
                ON metadata.id = response.response_metadata_id
            ORDER BY metadata.received_at DESC, metadata.id DESC
            """
        )
    ]


@log_timing(logger=logger, level=_timing_log_level)
def get_system_cost_indices(
    connection: Connection, response_metadata_id: int
) -> models.SystemCostIndicesDataset:
    """Get the system cost index dataset for a response metadata ID."""
    metadata = connection.execute(
        """
        SELECT metadata.id, metadata.received_at, metadata.expires_at,
               metadata.argus_expires_at
        FROM get_industry_systems_response AS response
        JOIN response_metadata AS metadata
            ON metadata.id = response.response_metadata_id
        WHERE metadata.id = ?
        """,
        (response_metadata_id,),
    ).fetchone()
    if metadata is None:
        raise ValueError(
            "No system cost indices response found for response metadata ID "
            f"{response_metadata_id}"
        )

    records = {
        row[0]: models.SystemCostIndexRecord(
            system_id=row[0],
            copying=from_four_places(row[1]) if row[1] is not None else None,
            manufacturing=from_four_places(row[2]) if row[2] is not None else None,
            invention=from_four_places(row[3]) if row[3] is not None else None,
            reaction=from_four_places(row[4]) if row[4] is not None else None,
            researching_material_efficiency=(
                from_four_places(row[5]) if row[5] is not None else None
            ),
            researching_time_efficiency=(
                from_four_places(row[6]) if row[6] is not None else None
            ),
            response_metadata_id=row[7],
        )
        for row in connection.execute(
            """
            SELECT system_id, copying, manufacturing, invention, reaction,
                   researching_material_efficiency,
                   researching_time_efficiency, response_metadata_id
            FROM system_cost_indices
            WHERE response_metadata_id = ?
            ORDER BY system_id
            """,
            (response_metadata_id,),
        )
    }

    return models.SystemCostIndicesDataset(
        response_metadata_id=metadata[0],
        received_at=metadata[1],
        expires_at=metadata[2],
        argus_expires_at=metadata[3],
        records=records,
    )


@log_timing(logger=logger, level=_timing_log_level)
def get_corporation_industry_jobs_responses(
    connection: Connection, corporation_id: int | None
) -> list[models.CorporationIndustryJobsResponse]:
    """Get metadata for stored corporation industry job responses."""
    query = """
        SELECT metadata.id, metadata.received_at, metadata.expires_at,
               metadata.argus_expires_at, response.corporation_id
        FROM get_corporations_corporation_id_industry_jobs_response AS response
        JOIN response_metadata AS metadata
            ON metadata.id = response.response_metadata_id
    """
    parameters: list[int] = []
    if corporation_id is not None:
        query += " WHERE response.corporation_id = ?"
        parameters.append(corporation_id)
    query += " ORDER BY metadata.received_at DESC, metadata.id DESC"

    return [
        models.CorporationIndustryJobsResponse(
            response_metadata_id=row[0],
            received_at=row[1],
            expires_at=row[2],
            argus_expires_at=row[3],
            corporation_id=row[4],
        )
        for row in connection.execute(query, parameters)
    ]


@log_timing(logger=logger, level=_timing_log_level)
def get_corporation_industry_jobs(
    connection: Connection, response_metadata_id: int
) -> models.CorporationIndustryJobsDataset:
    """Get the corporation industry jobs dataset for a response metadata ID."""
    metadata = connection.execute(
        """
        SELECT metadata.id, metadata.received_at, metadata.expires_at,
               metadata.argus_expires_at, response.corporation_id
        FROM get_corporations_corporation_id_industry_jobs_response AS response
        JOIN response_metadata AS metadata
            ON metadata.id = response.response_metadata_id
        WHERE metadata.id = ?
        """,
        (response_metadata_id,),
    ).fetchone()
    if metadata is None:
        raise ValueError(
            "No corporation industry jobs response found for response metadata ID "
            f"{response_metadata_id}"
        )

    records = {
        row[12]: models.CorporationIndustryJobRow(
            corporation_id=row[0],
            activity_id=row[1],
            blueprint_id=row[2],
            blueprint_location_id=row[3],
            blueprint_type_id=row[4],
            completed_character_id=row[5],
            completed_date=row[6],
            cost=from_cents(row[7]) if row[7] is not None else None,
            duration=row[8],
            end_date=row[9],
            facility_id=row[10],
            installer_id=row[11],
            job_id=row[12],
            licensed_runs=row[13],
            location_id=row[14],
            output_location_id=row[15],
            pause_date=row[16],
            probability=row[17],
            product_type_id=row[18],
            runs=row[19],
            start_date=row[20],
            status=row[21],
            successful_runs=row[22],
            response_metadata_id=row[23],
        )
        for row in connection.execute(
            """
            SELECT corporation_id, activity_id, blueprint_id,
                   blueprint_location_id, blueprint_type_id,
                   completed_character_id, completed_date, cost, duration,
                   end_date, facility_id, installer_id, job_id, licensed_runs,
                   location_id, output_location_id, pause_date, probability,
                   product_type_id, runs, start_date, status,
                   successful_runs, response_metadata_id
            FROM corporation_industry_jobs
            WHERE response_metadata_id = ?
            ORDER BY job_id
            """,
            (response_metadata_id,),
        )
    }

    return models.CorporationIndustryJobsDataset(
        response_metadata_id=metadata[0],
        received_at=metadata[1],
        expires_at=metadata[2],
        argus_expires_at=metadata[3],
        corporation_id=metadata[4],
        records=records,
    )


@log_timing(logger=logger, level=_timing_log_level)
def get_corporation_blueprints_responses(
    connection: Connection, corporation_id: int | None
) -> list[models.CorporationBlueprintsResponse]:
    """Get metadata for stored corporation blueprint responses."""
    query = """
        SELECT metadata.id, metadata.received_at, metadata.expires_at,
               metadata.argus_expires_at, response.corporation_id
        FROM get_corporations_corporation_id_blueprints_response AS response
        JOIN response_metadata AS metadata
            ON metadata.id = response.response_metadata_id
    """
    parameters: list[int] = []
    if corporation_id is not None:
        query += " WHERE response.corporation_id = ?"
        parameters.append(corporation_id)
    query += " ORDER BY metadata.received_at DESC, metadata.id DESC"

    return [
        models.CorporationBlueprintsResponse(
            response_metadata_id=row[0],
            received_at=row[1],
            expires_at=row[2],
            argus_expires_at=row[3],
            corporation_id=row[4],
        )
        for row in connection.execute(query, parameters)
    ]


@log_timing(logger=logger, level=_timing_log_level)
def get_corporation_blueprints(
    connection: Connection, response_metadata_id: int
) -> models.CorporationBlueprintsDataset:
    """Get the corporation blueprints dataset for a response metadata ID."""
    metadata = connection.execute(
        """
        SELECT metadata.id, metadata.received_at, metadata.expires_at,
               metadata.argus_expires_at, response.corporation_id
        FROM get_corporations_corporation_id_blueprints_response AS response
        JOIN response_metadata AS metadata
            ON metadata.id = response.response_metadata_id
        WHERE metadata.id = ?
        """,
        (response_metadata_id,),
    ).fetchone()
    if metadata is None:
        raise ValueError(
            "No corporation blueprints response found for response metadata ID "
            f"{response_metadata_id}"
        )

    records = {
        row[0]: models.CorporationBlueprintRecord(
            corporation_id=row[1],
            item_id=row[0],
            type_id=row[2],
            location_id=row[3],
            location_flag=row[4],
            quantity=row[5],
            time_efficiency=row[6],
            material_efficiency=row[7],
            runs=row[8],
            response_metadata_id=row[9],
        )
        for row in connection.execute(
            """
            SELECT item_id, corporation_id, type_id, location_id, location_flag,
                   quantity, time_efficiency, material_efficiency, runs,
                   response_metadata_id
            FROM corporation_blueprints
            WHERE response_metadata_id = ?
            ORDER BY item_id
            """,
            (response_metadata_id,),
        )
    }

    return models.CorporationBlueprintsDataset(
        response_metadata_id=metadata[0],
        received_at=metadata[1],
        expires_at=metadata[2],
        argus_expires_at=metadata[3],
        corporation_id=metadata[4],
        records=records,
    )
