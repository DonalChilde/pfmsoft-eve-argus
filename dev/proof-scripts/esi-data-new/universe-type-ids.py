"""Fetch and validate the universe type ID list using the new ESI package."""

from _shared import (
    create_resources,
    run_proof,
    save_raw_response,
    save_validated_response,
)

from pfmsoft.eve_argus.esi import fetch, validate


async def prove_universe_type_ids() -> None:
    """Exercise the paginated universe type ID fetch and matching validator."""
    async with create_resources() as resources:
        response = await fetch.universe_type_ids(
            resources.esi_link, resources.esi_schema
        )
        response = save_raw_response(response, name="universe-type-ids")
        save_validated_response(
            validate.universe_type_ids(response), name="universe-type-ids"
        )


if __name__ == "__main__":
    run_proof(prove_universe_type_ids(), name="universe-type-ids")
