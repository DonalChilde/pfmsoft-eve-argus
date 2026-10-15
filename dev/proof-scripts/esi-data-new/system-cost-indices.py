"""Fetch and validate industry system cost indices using the new ESI package."""

from _shared import (
    create_resources,
    run_proof,
    save_raw_response,
    save_validated_response,
)

from pfmsoft.eve_argus.esi import fetch, validate


async def prove_system_cost_indices() -> None:
    """Exercise the system cost indices fetch and its matching validator."""
    async with create_resources() as resources:
        response = await fetch.system_cost_indices(
            resources.esi_link, resources.esi_schema
        )
        response = save_raw_response(response, name="system-cost-indices")
        save_validated_response(
            validate.system_cost_indices(response), name="system-cost-indices"
        )


if __name__ == "__main__":
    run_proof(prove_system_cost_indices(), name="system-cost-indices")
