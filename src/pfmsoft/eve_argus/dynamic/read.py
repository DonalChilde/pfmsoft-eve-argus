"""Read dynamic data from the database."""

# All *_responses readers return newest received_at first; IDs break timestamp ties.
# The definition for this database lives at src/pfmsoft/eve_argus/dynamic/db/table_definitions.sql
import logging
from decimal import Decimal
from sqlite3 import Connection
from typing import Any

from pfmsoft.eve_argus.dynamic import models, order_summary
from pfmsoft.eve_argus.dynamic.order_summary import FILTER_FACTOR_DEFAULT
from pfmsoft.eve_argus.helpers.currency import (
    from_cents,
    from_four_places,
)
from pfmsoft.eve_argus.helpers.timing import log_timing

logger = logging.getLogger(__name__)


_timing_log_level = logging.INFO


@log_timing(logger=logger, level=_timing_log_level)
def order_summaries(
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
def order_summary_responses(
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
def response_metadata(
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
def markets_prices_responses(
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
def markets_prices(
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
def market_orders_responses(
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
def market_orders(
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
        f"""
        SELECT {_MARKET_ORDER_COLUMNS}
        FROM market_orders
        WHERE response_metadata_id = ?
        ORDER BY type_id, order_id
        """,
        (response_metadata_id,),
    ):
        order = _market_order_record(row)
        bucket = grouped_orders.setdefault(order.type_id, {"buy": [], "sell": []})
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
def market_orders_filtered(
    connection: Connection,
    response_metadata_id: int,
    *,
    type_id: int | None = None,
    system_id: int | None = None,
    location_id: int | None = None,
    is_buy_order: bool | None = None,
) -> tuple[models.MarketOrderRecord, ...]:
    """Get the filtered market orders dataset for a response metadata ID.

    This function retrieves market orders filtered by the specified criteria.
    If a filter parameter is None, it will not be applied.

    Note that response_metadata_id is always required and implies a region_id, as each
    response metadata ID corresponds to a request for market orders in that region.

    Args:
        connection: The database connection to use.
        response_metadata_id: The response metadata ID to filter by.
        type_id: Optional type ID to filter by.
        system_id: Optional system ID to filter by.
        location_id: Optional location ID to filter by.
        is_buy_order: Optional flag to filter by buy/sell orders. None means no filtering.

    Returns:
        A tuple of filtered market order records, ordered by type_id and order_id.
        An unknown response metadata ID produces an empty tuple.
    """
    filters: dict[str, int | None] = {
        "type_id": type_id,
        "system_id": system_id,
        "location_id": location_id,
        "is_buy_order": None if is_buy_order is None else int(is_buy_order),
    }
    conditions = ["response_metadata_id = ?"]
    parameters: list[int] = [response_metadata_id]
    for column, value in filters.items():
        if value is not None:
            conditions.append(f"{column} = ?")
            parameters.append(value)

    return tuple(
        _market_order_record(row)
        for row in connection.execute(
            f"""
            SELECT {_MARKET_ORDER_COLUMNS}
            FROM market_orders
            WHERE {" AND ".join(conditions)}
            ORDER BY type_id, order_id
            """,
            parameters,
        )
    )


@log_timing(logger=logger, level=_timing_log_level)
def calculate_market_order_summary(
    connection: Connection,
    response_metadata_id: int,
    *,
    type_id: int,
    system_id: int | None = None,
    location_id: int | None = None,
    is_buy_summary: bool = True,
    filter_factor: Decimal = FILTER_FACTOR_DEFAULT,
) -> models.OrderSummaryRecord | None:
    """Calculate one side of a type's order summary from a filtered query.

    Only the orders within the requested scope are read from the database, which
    avoids loading a whole region when a single summary is needed.

    Args:
        connection: The database connection to use.
        response_metadata_id: The market orders response to summarize.
        type_id: The item type to summarize.
        system_id: Limit the calculation to one solar system.
        location_id: Limit the calculation to one station or structure.
        is_buy_summary: True to summarize buy orders, False for sell orders.
        filter_factor: Exclude buy prices below best / factor and sell prices above
            best * factor. Must be greater than 1.

    Returns:
        The summary, or None if no orders with remaining volume match the query.

    Raises:
        ValueError: If both scopes are supplied or the factor is invalid.
    """
    order_summary.validate_summary_options(
        system_id=system_id, location_id=location_id, filter_factor=filter_factor
    )
    orders = market_orders_filtered(
        connection,
        response_metadata_id,
        type_id=type_id,
        system_id=system_id,
        location_id=location_id,
        is_buy_order=is_buy_summary,
    )
    if not orders:
        return None
    return order_summary.calculate_order_summary(
        orders,
        region_id=orders[0].region_id,
        type_id=type_id,
        system_id=system_id,
        location_id=location_id,
        is_buy_summary=is_buy_summary,
        filter_factor=filter_factor,
    )


_MARKET_ORDER_COLUMNS = """response_metadata_id, region_id, duration, is_buy_order,
               issued, location_id, min_volume, order_id, price, range_,
               system_id, type_id, volume_remain, volume_total"""


def _market_order_record(row: tuple[Any, ...]) -> models.MarketOrderRecord:
    """Convert a row selected with `_MARKET_ORDER_COLUMNS` into a record."""
    return models.MarketOrderRecord(
        response_metadata_id=row[0],
        region_id=row[1],
        duration=row[2],
        is_buy_order=bool(row[3]),
        issued=row[4],
        location_id=row[5],
        min_volume=row[6],
        order_id=row[7],
        price=from_cents(row[8]),
        range=row[9],
        system_id=row[10],
        type_id=row[11],
        volume_remain=row[12],
        volume_total=row[13],
    )


@log_timing(logger=logger, level=_timing_log_level)
def system_cost_indices_responses(
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
def system_cost_indices(
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
def corporation_industry_jobs_responses(
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
def corporation_industry_jobs(
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
def corporation_blueprints_responses(
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
def corporation_blueprints(
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
