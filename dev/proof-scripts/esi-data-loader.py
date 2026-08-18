"""Proof script for the ESI data loader.

This script demonstrates the usage of the ESI data loader by loading various ESI responses
and printing the results.
"""

import asyncio
from logging import getLogger
from pathlib import Path
from time import perf_counter_ns

from pfmsoft.eve_argus.data_loaders.esi_responses import EsiResponseLoader
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.settings import get_settings

logger = getLogger(__name__)
PROOF_OUTPUT_DIR = Path(__file__).parent / "proof-output"
PROOF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MARKET_GROUP_IDS_FILENAME = PROOF_OUTPUT_DIR / "market_group_ids_response.json"
MARKET_GROUPS_DETAILS_FILENAME = (
    PROOF_OUTPUT_DIR / "market_groups_details_collected_response.json"
)
REGION_MARKET_ORDERS_FILENAME = PROOF_OUTPUT_DIR / "region_market_orders_response.json"
REGION_MARKET_HISTORY_FILENAME = (
    PROOF_OUTPUT_DIR / "region_market_history_collected_response.json"
)
MARKETS_PRICES_FILENAME = PROOF_OUTPUT_DIR / "markets_prices_response.json"
INDUSTRY_SYSTEMS_FILENAME = PROOF_OUTPUT_DIR / "industry_systems_response.json"


async def prove_esi_data_loader():
    """Prove the ESI data loader by loading and printing ESI responses."""
    settings = get_settings()
    print(f"Using settings: {settings}")
    resource_manager = EveArgusResources(settings=settings)

    async with resource_manager as resources:
        esi_loader = EsiResponseLoader(
            esi_link=resources.esi_link, schema=resources.esi_schema
        )
        # Measure the time taken to load each dataset and print the results
        print()
        start_time = perf_counter_ns()
        market_group_ids_response = await esi_loader.market_group_ids()
        end_time = perf_counter_ns()
        filename = MARKET_GROUP_IDS_FILENAME
        filename.write_text(market_group_ids_response.serialize(indent=2))
        print(f"Saved market group IDs response to {filename}")
        print(
            f"Time taken to load market group IDs: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
        )
        print(
            f"Loaded {len(market_group_ids_response.response_data.market_group_ids)} market group IDs."
        )
        market_group_ids = set(market_group_ids_response.response_data.market_group_ids)

        print()
        start_time = perf_counter_ns()
        market_groups_details_response = await esi_loader.market_groups_details(
            market_group_ids=market_group_ids
        )
        end_time = perf_counter_ns()
        filename = MARKET_GROUPS_DETAILS_FILENAME
        filename.write_text(market_groups_details_response.serialize(indent=2))
        print(f"Saved market groups details collected response to {filename}")
        print(
            f"Time taken to load market groups details: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
        )
        print(
            f"Loaded details for {len(market_groups_details_response.response_data)} market groups."
        )

        print()
        start_time = perf_counter_ns()
        region_market_orders_response = await esi_loader.region_market_orders(
            region_id=10000002
        )
        end_time = perf_counter_ns()
        filename = REGION_MARKET_ORDERS_FILENAME
        filename.write_text(region_market_orders_response.serialize(indent=2))
        print(f"Saved region market orders response to {filename}")
        print(
            f"Time taken to load region market orders: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
        )
        print(
            f"Loaded {len(region_market_orders_response.response_data.orders)} market orders for region 10000002."
        )

        print()
        start_time = perf_counter_ns()
        region_market_history_response = await esi_loader.region_market_histories(
            region_id=10000002, type_ids={34, 35, 36}
        )
        end_time = perf_counter_ns()
        filename = REGION_MARKET_HISTORY_FILENAME
        filename.write_text(region_market_history_response.serialize(indent=2))
        print(f"Saved region market history collected response to {filename}")
        print(
            f"Time taken to load region market history: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
        )
        print(
            f"Loaded market history for {len(region_market_history_response.response_data)} types in region 10000002."
        )

        print()
        start_time = perf_counter_ns()
        markets_prices_response = await esi_loader.markets_prices()
        end_time = perf_counter_ns()
        filename = MARKETS_PRICES_FILENAME
        filename.write_text(markets_prices_response.serialize(indent=2))
        print(f"Saved markets prices response to {filename}")
        print(
            f"Time taken to load market prices: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
        )
        print(
            f"Loaded market prices for {len(markets_prices_response.response_data.markets_prices)} types."
        )

        print()
        start_time = perf_counter_ns()
        industry_systems_response = await esi_loader.industry_systems()
        end_time = perf_counter_ns()
        filename = INDUSTRY_SYSTEMS_FILENAME
        filename.write_text(industry_systems_response.serialize(indent=2))
        print(f"Saved industry systems response to {filename}")
        print(
            f"Time taken to load industry systems: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
        )
        print(
            f"Loaded {len(industry_systems_response.response_data.industry_systems)} industry systems."
        )


if __name__ == "__main__":
    # Run the proof script
    asyncio.run(prove_esi_data_loader())
