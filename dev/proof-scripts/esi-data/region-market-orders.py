"""Proof script for the regional market orders ESI response.

Loads the current market orders for a region from ESI.
"""

import asyncio
import sqlite3
from logging import getLogger
from time import perf_counter_ns

from _shared import PROOF_OUTPUT_DIR, create_resources, setup_logging

from pfmsoft.eve_argus.data_loaders.esi_responses import EsiResponseLoader
from pfmsoft.eve_argus.market.orders.db import query_helpers
from pfmsoft.eve_argus.models.esi import esi_response_models

logger = getLogger(__name__)

REGION_ID = 10000002
REGION_MARKET_ORDERS_FILENAME = PROOF_OUTPUT_DIR / "region_market_orders_response.json"


async def prove_region_market_orders() -> None:
    """Prove loading regional market orders from ESI."""
    async with create_resources() as resources:
        loader = EsiResponseLoader(
            esi_link=resources.esi_link, schema=resources.esi_schema
        )
        response = await region_market_orders(loader=loader, region_id=REGION_ID)
        write_to_db(
            connection=resources.order_db_connection,
            region_market_orders_response=response,
        )


async def region_market_orders(
    loader: EsiResponseLoader, region_id: int
) -> esi_response_models.GetMarketsRegionIdOrdersResponse:
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
    region_market_orders_response: esi_response_models.GetMarketsRegionIdOrdersResponse,
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


if __name__ == "__main__":
    log_filepath = setup_logging("region-market-orders")
    logger.info(f"Logging to {log_filepath}")
    asyncio.run(prove_region_market_orders())
