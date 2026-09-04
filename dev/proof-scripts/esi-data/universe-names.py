"""Proof script for universe names ESI responses.

Loads the universe type IDs, then resolves names for a sample of those IDs.
The names call depends on the type IDs from the first call, so both calls are
kept together in this script.
"""

import asyncio
from logging import getLogger
from time import perf_counter_ns

from _shared import PROOF_OUTPUT_DIR, create_esi_loader, setup_logging

from pfmsoft.eve_argus.data_loaders.esi_responses import EsiResponseLoader
from pfmsoft.eve_argus.models.esi import esi_response_models

logger = getLogger(__name__)

UNIVERSE_TYPE_IDS_FILENAME = PROOF_OUTPUT_DIR / "universe_type_ids_response.json"
UNIVERSE_NAMES_FILENAME = PROOF_OUTPUT_DIR / "universe_names_response.json"
TYPE_ID_SAMPLE_SIZE = 2000


async def prove_universe_names() -> None:
    """Prove loading universe type IDs and resolving names from ESI."""
    async with create_esi_loader() as loader:
        universe_type_ids_response = await universe_type_ids(loader=loader)
        first_2000_type_ids = set(
            universe_type_ids_response.response_data.type_ids[:TYPE_ID_SAMPLE_SIZE]
        )
        _ = await universe_names(loader=loader, ids=first_2000_type_ids)


async def universe_type_ids(
    loader: EsiResponseLoader,
) -> esi_response_models.GetUniverseTypesResponse:
    """Loads the universe type IDs from ESI."""
    print()
    start_time = perf_counter_ns()
    universe_type_ids_response = await loader.universe_type_ids()
    end_time = perf_counter_ns()
    filename = UNIVERSE_TYPE_IDS_FILENAME
    filename.write_text(universe_type_ids_response.serialize(indent=2))
    print(f"Saved universe type IDs response to {filename}")
    print(
        f"Time taken to load universe type IDs: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
    )
    print(
        f"Loaded {len(universe_type_ids_response.response_data.type_ids)} universe type IDs."
    )
    return universe_type_ids_response


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


if __name__ == "__main__":
    log_filepath = setup_logging("universe-names")
    logger.info(f"Logging to {log_filepath}")
    asyncio.run(prove_universe_names())
