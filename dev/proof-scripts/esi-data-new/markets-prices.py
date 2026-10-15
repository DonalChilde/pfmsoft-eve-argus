"""Fetch and validate market prices using the new ESI package."""

from _shared import (
    create_resources,
    run_proof,
    save_raw_response,
    save_validated_response,
)

from pfmsoft.eve_argus.esi import fetch, validate


async def prove_markets_prices() -> None:
    """Exercise the market prices fetch and its matching validator."""
    async with create_resources() as resources:
        response = await fetch.markets_prices(resources.esi_link, resources.esi_schema)
        response = save_raw_response(response, name="markets-prices")
        save_validated_response(
            validate.markets_prices(response), name="markets-prices"
        )


if __name__ == "__main__":
    run_proof(prove_markets_prices(), name="markets-prices")
