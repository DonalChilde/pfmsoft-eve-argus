"""Fetch and validate names for sample universe IDs using the new ESI package."""

from _shared import (
    create_resources,
    run_proof,
    save_raw_response,
    save_validated_response,
)

from pfmsoft.eve_argus.esi import fetch, validate

IDS = {34, 35, 36, 10000002}


async def prove_universe_names() -> None:
    """Exercise the list-returning names fetch and its matching validator."""
    async with create_resources() as resources:
        responses = await fetch.universe_names(
            resources.esi_link, resources.esi_schema, ids=IDS
        )
        if not responses:
            raise RuntimeError("No universe names responses were returned.")
        successful_responses = [
            save_raw_response(response, name=f"universe-names-batch-{index}")
            for index, response in enumerate(responses, start=1)
        ]
        save_validated_response(
            validate.universe_names(successful_responses), name="universe-names"
        )


if __name__ == "__main__":
    run_proof(prove_universe_names(), name="universe-names")
