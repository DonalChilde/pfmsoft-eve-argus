"""Proof script for the ESI data loader.

This script demonstrates the usage of the ESI data loader by loading various ESI responses
and printing the results.
"""

import asyncio
import json
from dataclasses import asdict
from logging import basicConfig, getLogger
from pathlib import Path
from time import perf_counter_ns
from typing import TypedDict
from uuid import UUID

from pfmsoft.eve_argus.data_loaders.esi_responses import EsiResponseLoader
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.models.esi import esi_response_models
from pfmsoft.eve_argus.reports.corp_industry_jobs import (
    CollectedIds,
    CollectedIdsRoot,
    CorporationIndustryJobsNamed,
    CorporationIndustryJobsNamedRoot,
    collect_ids_for_lookup,
    create_corporation_industry_jobs_named,
)
from pfmsoft.eve_argus.settings import get_settings

logger = getLogger(__name__)


class SampleAuthData(TypedDict):
    character_id: int
    corporation_id: int
    cred_id: UUID


PROOF_OUTPUT_DIR = Path(__file__).parent / "proof-output" / "esi-data-loader"
PROOF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DEV_SECRETS_DIR = Path(__file__).parent.parent / "secrets"
LOGGING_DIR = Path(__file__).parent / "logging"
LOGGING_DIR.mkdir(parents=True, exist_ok=True)
LOGGING_FILEPATH = LOGGING_DIR / "esi-data-loader.log"
basicConfig(filename=LOGGING_FILEPATH, level="INFO")

MARKET_GROUP_IDS_FILENAME = PROOF_OUTPUT_DIR / "market_group_ids_response.json"
logger.info(f"Logging to {LOGGING_FILEPATH}")
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
CORPORATION_INDUSTRY_JOBS_IDS_FILENAME = (
    PROOF_OUTPUT_DIR / "corporation_industry_jobs_ids.json"
)
CORPORATION_INDUSTRY_JOBS_UNIVERSE_NAMES_FILENAME = (
    PROOF_OUTPUT_DIR / "corporation_industry_jobs_universe_names_response.json"
)
CORPORATION_INDUSTRY_JOBS_NAMED_FILENAME = (
    PROOF_OUTPUT_DIR / "corporation_industry_jobs_named.json"
)


async def prove_esi_data_loader(sample_auth_data: SampleAuthData | None = None) -> None:
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

        universe_type_ids_response = await universe_type_ids(loader=esi_loader)

        first_2000_type_ids = set(
            universe_type_ids_response.response_data.type_ids[:2000]
        )
        _ = await universe_names(loader=esi_loader, ids=first_2000_type_ids)
        if sample_auth_data:
            corporation_industry_jobs_response = await corporation_industry_jobs(
                loader=esi_loader,
                corporation_id=sample_auth_data["corporation_id"],
                character_id=sample_auth_data["character_id"],
                credential_id=sample_auth_data["cred_id"],
            )
            corp_jobs_named = await corporation_industry_jobs_named(
                corporation_industry_jobs_response=corporation_industry_jobs_response,
                loader=esi_loader,
            )
            print()
            root_model = CorporationIndustryJobsNamedRoot(root=corp_jobs_named)
            CORPORATION_INDUSTRY_JOBS_NAMED_FILENAME.write_text(
                root_model.model_dump_json(indent=2)
            )
            print(
                f"Saved corporation industry jobs named response to {CORPORATION_INDUSTRY_JOBS_NAMED_FILENAME}"
            )


async def corporation_industry_jobs_named(
    corporation_industry_jobs_response: esi_response_models.GetCorporationsCorporationIdIndustryJobsResponse,
    loader: EsiResponseLoader,
) -> CorporationIndustryJobsNamed:
    corp_jobs_ids = collect_corporation_industry_jobs_ids(
        corporation_industry_jobs_response
    )
    corp_jobs_universe_names = await corporation_industry_jobs_universe_names(
        corp_jobs_ids=corp_jobs_ids.universe_ids, loader=loader
    )
    corp_jobs_names_dict = {
        name.id: name.name for name in corp_jobs_universe_names.response_data.names
    }

    corp_jobs_named = create_corporation_industry_jobs_named(
        jobs=corporation_industry_jobs_response.response_data,
        names=corp_jobs_names_dict,
    )
    return corp_jobs_named


async def corporation_industry_jobs_universe_names(
    corp_jobs_ids: set[int], loader: EsiResponseLoader
) -> esi_response_models.PostUniverseNamesResponse:
    """Loads the universe names for the given corporation industry jobs IDs from ESI."""
    print()
    start_time = perf_counter_ns()
    universe_names_response = await loader.universe_names(ids=corp_jobs_ids)
    end_time = perf_counter_ns()
    CORPORATION_INDUSTRY_JOBS_UNIVERSE_NAMES_FILENAME.write_text(
        universe_names_response.serialize(indent=2)
    )
    print(
        f"Saved corporation industry jobs universe names response to {CORPORATION_INDUSTRY_JOBS_UNIVERSE_NAMES_FILENAME}"
    )
    print(
        f"Time taken to load corporation industry jobs universe names: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
    )
    return universe_names_response


def collect_corporation_industry_jobs_ids(
    corporation_industry_jobs_response: esi_response_models.GetCorporationsCorporationIdIndustryJobsResponse,
) -> CollectedIds:
    """Loads and collects the IDs for corporation industry jobs from the given response."""
    print()
    collected_ids = collect_ids_for_lookup(
        corporation_industry_jobs_response.response_data
    )
    print(
        f"Found {len(collected_ids.universe_ids)} universe IDs and {len(collected_ids.corporation_ids)} corporation IDs."
    )
    CORPORATION_INDUSTRY_JOBS_IDS_FILENAME.write_text(
        CollectedIdsRoot(root=collected_ids).model_dump_json(indent=2)
    )
    return collected_ids


async def universe_type_ids(
    loader: EsiResponseLoader,
) -> esi_response_models.GetUniverseTypesResponse:
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
) -> esi_response_models.GetCorporationsCorporationIdIndustryJobsResponse:
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
) -> esi_response_models.PostUniverseNamesResponse:
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
) -> esi_response_models.GetMarketsGroupsMarketGroupIdCollectedResponse:
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
) -> esi_response_models.GetMarketsGroupsResponse:
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


async def region_market_history(
    loader: EsiResponseLoader, region_id: int, type_ids: set[int]
) -> esi_response_models.GetMarketsRegionIdHistoryCollectedResponse:
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
) -> esi_response_models.GetMarketsPricesResponse:
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
) -> esi_response_models.GetIndustrySystemsResponse:
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


def get_sample_auth_data() -> SampleAuthData | None:
    """Loads sample auth data from the secrets directory."""
    sample_auth_filepath = DEV_SECRETS_DIR / "auth.json"
    if not sample_auth_filepath.exists():
        logger.warning(f"Sample auth file {sample_auth_filepath} does not exist.")
        return None
    sample_auth_data = json.loads(sample_auth_filepath.read_text())
    return SampleAuthData(
        character_id=sample_auth_data["character_id"],
        corporation_id=sample_auth_data["corporation_id"],
        cred_id=UUID(sample_auth_data["cred_id"]),
    )


if __name__ == "__main__":
    sample_auth_data = get_sample_auth_data()
    print(f"Using sample auth data: {sample_auth_data}")
    # Run the proof script
    asyncio.run(prove_esi_data_loader(sample_auth_data=sample_auth_data))
