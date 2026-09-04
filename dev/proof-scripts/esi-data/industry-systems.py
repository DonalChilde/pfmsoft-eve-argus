"""Proof script for the industry systems ESI response.

Loads the industry systems cost indices from ESI.
"""

import asyncio
from logging import getLogger
from time import perf_counter_ns

from _shared import PROOF_OUTPUT_DIR, create_esi_loader, setup_logging

from pfmsoft.eve_argus.data_loaders.esi_responses import EsiResponseLoader
from pfmsoft.eve_argus.models.esi import esi_response_models

logger = getLogger(__name__)

INDUSTRY_SYSTEMS_FILENAME = PROOF_OUTPUT_DIR / "industry_systems_response.json"


async def prove_industry_systems() -> None:
    """Prove loading industry systems from ESI."""
    async with create_esi_loader() as loader:
        _ = await industry_systems(loader=loader)


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


if __name__ == "__main__":
    log_filepath = setup_logging("industry-systems")
    logger.info(f"Logging to {log_filepath}")
    asyncio.run(prove_industry_systems())
