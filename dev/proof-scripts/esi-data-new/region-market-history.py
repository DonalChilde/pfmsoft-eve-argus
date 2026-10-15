"""Fetch and validate regional market history for three mineral types."""

from _shared import (
    create_resources,
    run_proof,
    save_raw_response,
    save_validated_response,
)

from pfmsoft.eve_argus.esi import fetch, validate

REGION_ID = 10000002
TYPE_IDS = {34, 35, 36}


async def prove_market_history() -> None:
    """Exercise the single-type history fetch for each sample type in The Forge."""
    async with create_resources() as resources:
        for type_id in sorted(TYPE_IDS):
            name = f"region-market-history-{REGION_ID}-{type_id}"
            response = await fetch.market_history(
                resources.esi_link,
                resources.esi_schema,
                region_id=REGION_ID,
                type_id=type_id,
            )
            response = save_raw_response(response, name=name)
            save_validated_response(validate.market_history(response), name=name)


if __name__ == "__main__":
    run_proof(prove_market_history(), name="region-market-history")
