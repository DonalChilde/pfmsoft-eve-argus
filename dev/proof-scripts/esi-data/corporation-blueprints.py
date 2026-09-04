"""Proof script for the corporation blueprints ESI response.

Loads the corporation blueprints (an authorized endpoint requiring the Director
role) from ESI. Requires sample auth data from the dev secrets directory; the
script exits without loading data if none is available.
"""

import asyncio
from logging import getLogger
from time import perf_counter_ns
from uuid import UUID

from _shared import (
    PROOF_OUTPUT_DIR,
    create_esi_loader,
    get_sample_auth_data,
    setup_logging,
)

from pfmsoft.eve_argus.data_loaders.esi_responses import EsiResponseLoader
from pfmsoft.eve_argus.models.esi import esi_response_models

logger = getLogger(__name__)

CORPORATION_BLUEPRINTS_FILENAME = (
    PROOF_OUTPUT_DIR / "corporation_blueprints_response.json"
)


async def prove_corporation_blueprints() -> None:
    """Prove loading corporation blueprints from ESI."""
    sample_auth_data = get_sample_auth_data()
    print(f"Using sample auth data: {sample_auth_data}")
    if sample_auth_data is None:
        print("No sample auth data available, skipping corporation blueprints.")
        return

    async with create_esi_loader() as loader:
        _ = await corporation_blueprints(
            loader=loader,
            corporation_id=sample_auth_data["corporation_id"],
            character_id=sample_auth_data["character_id"],
            credential_id=sample_auth_data["cred_id"],
        )


async def corporation_blueprints(
    loader: EsiResponseLoader,
    corporation_id: int,
    character_id: int,
    credential_id: UUID,
) -> esi_response_models.GetCorporationsCorporationIdBlueprintsResponse:
    """Loads the corporation blueprints from ESI."""
    print()
    start_time = perf_counter_ns()
    corporation_blueprints_response = await loader.corporation_blueprints(
        corporation_id=corporation_id,
        character_id=character_id,
        credential_id=credential_id,
    )
    end_time = perf_counter_ns()
    filename = CORPORATION_BLUEPRINTS_FILENAME
    filename.write_text(corporation_blueprints_response.serialize(indent=2))
    print(f"Saved corporation blueprints response to {filename}")
    print(
        f"Time taken to load corporation blueprints: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
    )
    print(
        f"Loaded {len(corporation_blueprints_response.response_data.blueprints)} corporation blueprints."
    )
    return corporation_blueprints_response


if __name__ == "__main__":
    log_filepath = setup_logging("corporation-blueprints")
    logger.info(f"Logging to {log_filepath}")
    asyncio.run(prove_corporation_blueprints())
