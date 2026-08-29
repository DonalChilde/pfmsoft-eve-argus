"""Proof script for the ESI data loader.

This script demonstrates the usage of the ESI data loader by loading various ESI responses
and printing the results.
"""

import asyncio
from logging import getLogger
from pathlib import Path
from time import perf_counter_ns
from uuid import UUID

from pfmsoft.eve_argus.data_loaders.esi_responses import EsiResponseLoader
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.models.esi import esi_response
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
UNIVERSE_NAMES_FILENAME = PROOF_OUTPUT_DIR / "universe_names_response.json"
CORPORATION_INDUSTRY_JOBS_FILENAME = (
    PROOF_OUTPUT_DIR / "corporation_industry_jobs_response.json"
)


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

        market_group_ids_response = await market_group_ids(loader=esi_loader)
        market_group_ids_set = set(
            market_group_ids_response.response_data.market_group_ids
        )
        _ = await market_groups_details(
            loader=esi_loader, market_group_ids=market_group_ids_set
        )
        _ = await region_market_orders(loader=esi_loader, region_id=10000002)
        _ = await region_market_history(
            loader=esi_loader, region_id=10000002, type_ids={34, 35, 36}
        )
        _ = await markets_prices(loader=esi_loader)
        _ = await industry_systems(loader=esi_loader)
        _ = await universe_names(loader=esi_loader, ids={34, 35, 36, 37, 38})
        _ = await universe_type_ids(loader=esi_loader)


async def universe_type_ids(
    loader: EsiResponseLoader,
) -> esi_response.GetUniverseTypesResponse:
    """Loads the universe type IDs from ESI."""
    print()
    start_time = perf_counter_ns()
    universe_type_ids_response = await loader.universe_type_ids()
    end_time = perf_counter_ns()
    filename = PROOF_OUTPUT_DIR / "universe_type_ids_response.json"
    filename.write_text(universe_type_ids_response.serialize(indent=2))
    print(f"Saved universe type IDs response to {filename}")
    print(
        f"Time taken to load universe type IDs: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
    )
    print(
        f"Loaded {len(universe_type_ids_response.response_data.type_ids)} universe type IDs."
    )
    return universe_type_ids_response


async def corporation_industry_jobs(
    loader: EsiResponseLoader,
    corporation_id: int,
    character_id: int,
    credential_id: UUID,
) -> esi_response.GetCorporationsCorporationIdIndustryJobsResponse:
    """Loads the corporation industry jobs from ESI."""
    print()
    start_time = perf_counter_ns()
    corporation_industry_jobs_response = await loader.corporation_industry_jobs(
        corporation_id=corporation_id,
        character_id=character_id,
        credential_id=credential_id,
    )
    end_time = perf_counter_ns()
    filename = CORPORATION_INDUSTRY_JOBS_FILENAME
    filename.write_text(corporation_industry_jobs_response.serialize(indent=2))
    print(f"Saved corporation industry jobs response to {filename}")
    print(
        f"Time taken to load corporation industry jobs: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
    )
    print(
        f"Loaded {len(corporation_industry_jobs_response.response_data.industry_jobs)} corporation industry jobs."
    )
    return corporation_industry_jobs_response


async def universe_names(
    loader: EsiResponseLoader, ids: set[int]
) -> esi_response.PostUniverseNamesResponse:
    """Loads the universe names for the given IDs from ESI."""
    print()
    start_time = perf_counter_ns()
    universe_names_response = await loader.universe_names(ids=ids)
    end_time = perf_counter_ns()
    filename = UNIVERSE_NAMES_FILENAME
    filename.write_text(universe_names_response.serialize(indent=2))
    print(f"Saved universe names response to {filename}")
    print(
        f"Time taken to load universe names: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
    )
    print(f"Loaded {len(universe_names_response.response_data.names)} universe names.")
    return universe_names_response


async def market_groups_details(
    loader: EsiResponseLoader, market_group_ids: set[int]
) -> esi_response.GetMarketsGroupsMarketGroupIdCollectedResponse:
    """Loads the market group details from ESI."""
    print()
    start_time = perf_counter_ns()
    market_groups_details_response = await loader.market_groups_details(
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
    return market_groups_details_response


async def market_group_ids(
    loader: EsiResponseLoader,
) -> esi_response.GetMarketsGroupsResponse:
    """Loads the market group IDs from ESI."""
    print()
    start_time = perf_counter_ns()
    market_group_ids_response = await loader.market_group_ids()
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
    return market_group_ids_response


async def region_market_orders(
    loader: EsiResponseLoader, region_id: int
) -> esi_response.GetMarketsRegionIdOrdersResponse:
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


async def region_market_history(
    loader: EsiResponseLoader, region_id: int, type_ids: set[int]
) -> esi_response.GetMarketsRegionIdHistoryCollectedResponse:
    """Loads the market history for a region and types from ESI."""
    print()
    start_time = perf_counter_ns()
    region_market_history_response = await loader.region_market_histories(
        region_id=region_id, type_ids=type_ids
    )
    end_time = perf_counter_ns()
    filename = REGION_MARKET_HISTORY_FILENAME
    filename.write_text(region_market_history_response.serialize(indent=2))
    print(f"Saved region market history collected response to {filename}")
    print(
        f"Time taken to load region market history: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
    )
    print(
        f"Loaded market history for {len(region_market_history_response.response_data)} types in region {region_id}."
    )
    return region_market_history_response


async def markets_prices(
    loader: EsiResponseLoader,
) -> esi_response.GetMarketsPricesResponse:
    """Loads the market prices from ESI."""
    print()
    start_time = perf_counter_ns()
    markets_prices_response = await loader.markets_prices()
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
    return markets_prices_response


async def industry_systems(
    loader: EsiResponseLoader,
) -> esi_response.GetIndustrySystemsResponse:
    """Loads the industry systems from ESI."""
    print()
    start_time = perf_counter_ns()
    industry_systems_response = await loader.industry_systems()
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
    return industry_systems_response


if __name__ == "__main__":
    # Run the proof script
    asyncio.run(prove_esi_data_loader())
