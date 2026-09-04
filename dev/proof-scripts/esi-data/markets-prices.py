"""Proof script for the markets prices ESI response.

Loads the global market prices from ESI.
"""

import asyncio
from logging import getLogger
from time import perf_counter_ns

from _shared import PROOF_OUTPUT_DIR, create_esi_loader, setup_logging

from pfmsoft.eve_argus.data_loaders.esi_responses import EsiResponseLoader
from pfmsoft.eve_argus.models.esi import esi_response_models

logger = getLogger(__name__)

MARKETS_PRICES_FILENAME = PROOF_OUTPUT_DIR / "markets_prices_response.json"


async def prove_markets_prices() -> None:
    """Prove loading market prices from ESI."""
    async with create_esi_loader() as loader:
        _ = await markets_prices(loader=loader)


async def markets_prices(
    loader: EsiResponseLoader,
) -> esi_response_models.GetMarketsPricesResponse:
    """Loads the market prices from ESI."""
    print()
    start_time = perf_counter_ns()
    markets_prices_response = await loader.markets_prices()
    end_time = perf_counter_ns()
    filename = MARKETS_PRICES_FILENAME
    filename.write_text(markets_prices_response.serialize(indent=2))
    print(f"Saved markets prices response to {filename}")
    print(
        f"Time taken to load market prices: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
    )
    print(
        f"Loaded market prices for {len(markets_prices_response.response_data.markets_prices)} types."
    )
    return markets_prices_response


if __name__ == "__main__":
    log_filepath = setup_logging("markets-prices")
    logger.info(f"Logging to {log_filepath}")
    asyncio.run(prove_markets_prices())
