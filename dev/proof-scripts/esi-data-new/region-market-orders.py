"""Fetch and validate all regional market orders in The Forge."""

from _shared import (
    create_resources,
    run_proof,
    save_raw_response,
    save_validated_response,
)

from pfmsoft.eve_argus.esi import fetch, validate

REGION_ID = 10000002


async def prove_region_market_orders() -> None:
    """Exercise the region order fetch, including the client's pagination."""
    async with create_resources() as resources:
        response = await fetch.region_market_orders(
            resources.esi_link, resources.esi_schema, region_id=REGION_ID
        )
        response = save_raw_response(response, name="region-market-orders")
        save_validated_response(
            validate.region_market_orders(response), name="region-market-orders"
        )


if __name__ == "__main__":
    run_proof(prove_region_market_orders(), name="region-market-orders")
