"""Proof script for market group ESI responses.

Loads the market group IDs, then loads the details for each market group.
The details call depends on the IDs from the first call, so both calls are
kept together in this script.
"""

import asyncio
from logging import getLogger
from time import perf_counter_ns

from _shared import PROOF_OUTPUT_DIR, create_resources, setup_logging

from pfmsoft.eve_argus.data_loaders.esi_responses import EsiResponseLoader
from pfmsoft.eve_argus.models.esi import esi_response_models

logger = getLogger(__name__)

MARKET_GROUP_IDS_FILENAME = PROOF_OUTPUT_DIR / "market_group_ids_response.json"
MARKET_GROUPS_DETAILS_FILENAME = (
    PROOF_OUTPUT_DIR / "market_groups_details_collected_response.json"
)


async def prove_market_groups() -> None:
    """Prove loading market group IDs and market group details from ESI."""
    async with create_resources() as resources:
        loader = EsiResponseLoader(
            esi_link=resources.esi_link, schema=resources.esi_schema
        )
        market_group_ids_response = await market_group_ids(loader=loader)
        market_group_ids_set = set(
            market_group_ids_response.response_data.market_group_ids
        )
        _ = await market_groups_details(
            loader=loader, market_group_ids=market_group_ids_set
        )


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


if __name__ == "__main__":
    log_filepath = setup_logging("market-groups")
    logger.info(f"Logging to {log_filepath}")
    asyncio.run(prove_market_groups())
