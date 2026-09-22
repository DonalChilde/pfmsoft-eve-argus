"""Proof script for the regional market orders ESI response.

Loads the current market orders for a region from ESI.
"""

import asyncio
import sqlite3
from logging import getLogger
from time import perf_counter_ns

from _shared import PROOF_OUTPUT_DIR, create_resources, setup_logging

from pfmsoft.eve_argus.data_loaders.esi_responses import EsiResponseLoader
from pfmsoft.eve_argus.data_transform.order_summaries import (
    OrderSummaryReport,
    calculate_summaries,
)
from pfmsoft.eve_argus.market.orders.db import query_helpers
from pfmsoft.eve_argus.models.esi import argus_response_models as ARM
from pfmsoft.eve_argus.models.esi import esi_response_models as ERM

logger = getLogger(__name__)

REGION_ID = 10000002
REGION_MARKET_ORDERS_FILENAME = PROOF_OUTPUT_DIR / "region_market_orders_response.json"
REGION_MARKET_ORDERS_SUMMARY_FILENAME = (
    PROOF_OUTPUT_DIR / "region_market_orders_summary.json"
)


async def prove_region_market_orders() -> None:
    """Prove loading regional market orders from ESI."""
    async with create_resources() as resources:
        loader = EsiResponseLoader(
            esi_link=resources.esi_link, schema=resources.esi_schema
        )
        response = await fetch_region_market_orders(loader=loader, region_id=REGION_ID)
        write_to_db(
            connection=resources.order_db_connection,
            region_market_orders_response=response,
        )
        order_response, orders = load_region_market_orders_list_from_db(
            connection=resources.order_db_connection,
            region_id=REGION_ID,
        )
        total_count, order_count_by_system = load_order_count_by_system_from_db(
            connection=resources.order_db_connection,
            region_id=REGION_ID,
        )
        region_market_orders = load_region_market_orders_from_db(
            connection=resources.order_db_connection,
            order_response=order_response,
        )
        order_summary_report = calculate_order_summary_report(region_market_orders)


async def fetch_region_market_orders(
    loader: EsiResponseLoader, region_id: int
) -> ERM.GetMarketsRegionIdOrdersResponse:
    """Loads the market orders for a region from ESI."""
    print()
    start_time = perf_counter_ns()
    region_market_orders_response = await loader.region_market_orders(
        region_id=region_id
    )
    end_time = perf_counter_ns()
    filename = REGION_MARKET_ORDERS_FILENAME
    filename.write_text(region_market_orders_response.serialize(indent=2))
    print(f"Saved region market orders response to {filename}")
    print(
        f"Time taken to load region market orders: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
    )
    print(
        f"Loaded {len(region_market_orders_response.response_data.orders)} market orders for region {region_id}."
    )
    return region_market_orders_response


def write_to_db(
    connection: sqlite3.Connection,
    region_market_orders_response: ERM.GetMarketsRegionIdOrdersResponse,
) -> None:
    """Write the regional market orders response to the database."""
    start = perf_counter_ns()
    query_helpers.write_market_orders(
        connection, region_market_orders_response.response_data
    )
    end = perf_counter_ns()
    print(
        f"Time taken to write region market orders to the database: {(end - start) / 1_000_000_000:.6f} seconds"
    )


def calculate_order_summary_report(
    region_market_orders: ARM.RegionMarketOrders,
) -> OrderSummaryReport:
    """Calculate the order summary report for a given region market orders."""
    start = perf_counter_ns()
    report = calculate_summaries(region_market_orders)
    end = perf_counter_ns()
    print(
        f"Calculated order summary report for region {region_market_orders.region_id} in {(end - start) / 1_000_000_000:.6f} seconds"
    )
    REGION_MARKET_ORDERS_SUMMARY_FILENAME.write_text(report.serialize(indent=2))
    print(
        f"Saved region market orders summary to {REGION_MARKET_ORDERS_SUMMARY_FILENAME}"
    )
    return report


def load_region_market_orders_list_from_db(
    connection: sqlite3.Connection, region_id: int
) -> tuple[query_helpers.OrderResponse, list[ARM.MarketOrderDetail]]:
    """Load the regional market orders for a given region from the database."""
    start = perf_counter_ns()
    order_response = query_helpers.get_order_response(connection, region_id)
    print(
        f"Loaded order response from db for region {region_id} in {(perf_counter_ns() - start) / 1_000_000_000:.6f} seconds"
    )
    start = perf_counter_ns()
    region_market_orders = query_helpers.get_region_orders(connection, region_id)
    print(
        f"Loaded {len(region_market_orders)} region market orders from db for region {region_id} in {(perf_counter_ns() - start) / 1_000_000_000:.6f} seconds"
    )
    return order_response, region_market_orders


def load_region_market_orders_from_db(
    connection: sqlite3.Connection, order_response: query_helpers.OrderResponse
) -> ARM.RegionMarketOrders:
    """Load the regional market orders for a given region from the database."""
    start = perf_counter_ns()
    region_market_orders = query_helpers.get_region_market_orders(
        connection, order_response
    )
    print(
        f"Loaded region market orders from db for region {order_response.region_id} in {(perf_counter_ns() - start) / 1_000_000_000:.6f} seconds"
    )
    return region_market_orders


def load_order_count_by_system_from_db(
    connection: sqlite3.Connection, region_id: int
) -> tuple[int, list[query_helpers.OrderCountBySystem]]:
    """Load the order count by system for a given region from the database."""
    start = perf_counter_ns()
    total_count, results = query_helpers.get_order_count_by_system(
        connection, region_id
    )
    print(
        f"Loaded order count by system from db for region {region_id} in {(perf_counter_ns() - start) / 1_000_000_000:.6f} seconds"
    )
    print(f"Total order count for region {region_id}: {total_count}")
    for item in results:
        print(
            f"System {item.system_id}: {item.buy_orders} buy orders, {item.sell_orders} sell orders"
        )
    return total_count, results


if __name__ == "__main__":
    log_filepath = setup_logging("region-market-orders")
    logger.info(f"Logging to {log_filepath}")
    asyncio.run(prove_region_market_orders())
