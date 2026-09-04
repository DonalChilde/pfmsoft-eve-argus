"""Proof script for the regional market history ESI response.

Loads the market history for a set of type IDs in a region from ESI.
"""

import asyncio
from logging import getLogger
from time import perf_counter_ns

from _shared import PROOF_OUTPUT_DIR, create_resources, setup_logging

from pfmsoft.eve_argus.data_loaders.esi_responses import EsiResponseLoader
from pfmsoft.eve_argus.models.esi import esi_response_models

logger = getLogger(__name__)

REGION_ID = 10000002
TYPE_IDS = {34, 35, 36}
REGION_MARKET_HISTORY_FILENAME = (
    PROOF_OUTPUT_DIR / "region_market_history_collected_response.json"
)


async def prove_region_market_history() -> None:
    """Prove loading regional market history from ESI."""
    async with create_resources() as resources:
        loader = EsiResponseLoader(
            esi_link=resources.esi_link, schema=resources.esi_schema
        )
        _ = await region_market_history(
            loader=loader, region_id=REGION_ID, type_ids=TYPE_IDS
        )


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


if __name__ == "__main__":
    log_filepath = setup_logging("region-market-history")
    logger.info(f"Logging to {log_filepath}")
    asyncio.run(prove_region_market_history())
