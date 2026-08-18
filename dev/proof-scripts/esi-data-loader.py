import asyncio
from logging import getLogger
from time import perf_counter_ns

from pfmsoft.eve_argus.data_loaders.esi_responses import EsiResponseLoader
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.settings import get_settings

logger = getLogger(__name__)


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

        start_time = perf_counter_ns()
        market_group_ids_response = await esi_loader.market_group_ids()
        end_time = perf_counter_ns()
        print(
            f"Time taken to load market group IDs: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
        )
        print(f"Loaded {len(market_group_ids_response.group_ids)} market group IDs.")
        market_group_ids = set(market_group_ids_response.group_ids)

        start_time = perf_counter_ns()
        market_groups_details_response = await esi_loader.market_groups_details(
            market_group_ids=market_group_ids
        )
        end_time = perf_counter_ns()
        print(
            f"Time taken to load market groups details: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
        )
        print(
            f"Loaded details for {len(market_groups_details_response)} market groups."
        )

        start_time = perf_counter_ns()
        region_market_orders_response = await esi_loader.region_market_orders(
            region_id=10000002
        )
        end_time = perf_counter_ns()
        print(
            f"Time taken to load region market orders: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
        )
        print(
            f"Loaded {len(region_market_orders_response.orders)} market orders for region 10000002."
        )

        start_time = perf_counter_ns()
        region_market_history_response = await esi_loader.region_market_histories(
            region_id=10000002, type_ids={34, 35, 36}
        )
        end_time = perf_counter_ns()
        print(
            f"Time taken to load region market history: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
        )
        print(
            f"Loaded market history for {len(region_market_history_response)} types in region 10000002."
        )

        start_time = perf_counter_ns()
        markets_prices_response = await esi_loader.markets_prices()
        end_time = perf_counter_ns()
        print(
            f"Time taken to load market prices: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
        )
        print(f"Loaded market prices for {len(markets_prices_response.prices)} types.")

        start_time = perf_counter_ns()
        industry_systems_response = await esi_loader.industry_systems()
        end_time = perf_counter_ns()
        print(
            f"Time taken to load industry systems: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
        )
        print(f"Loaded {len(industry_systems_response.systems)} industry systems.")


if __name__ == "__main__":
    # Run the proof script
    asyncio.run(prove_esi_data_loader())
