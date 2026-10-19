"""Top-level package for Eve Argus ESI fetch operations.

This package contains functionality for fetching ESI data and updating the appropriate
database accordingly.

For functions that update the dynamic database:
 - The database will be checked for existing data.
 - If existing data is found and it is not expired, updates will be skipped.
 - If existing data is not found or is expired, updates will be performed.
 - A results object will be returned indicating the outcome of the update operations.

For functions that update the market history database:
 - The database will be checked for existing data for the region/type pair.
 - If existing data is found and it is not expired, updates will be skipped.
 - If existing data is not found or is expired, updates will be performed.
 - A results object will be returned indicating the outcome of the update operations.

Market-history updates retain older dates absent from subsequent responses and
replace overlapping daily records. Metadata and records are written transactionally.
Repeated responses already stored for the pair are reported as failed updates.
"""

from pfmsoft.eve_argus.fetch_esi.corporation_blueprints import (
    update_corporation_blueprints,
)
from pfmsoft.eve_argus.fetch_esi.corporation_industry_jobs import (
    update_corporation_industry_jobs,
)
from pfmsoft.eve_argus.fetch_esi.market_history import update_market_history
from pfmsoft.eve_argus.fetch_esi.market_history_bulk import update_market_histories
from pfmsoft.eve_argus.fetch_esi.market_orders import update_market_orders
from pfmsoft.eve_argus.fetch_esi.markets_prices import update_markets_prices
from pfmsoft.eve_argus.fetch_esi.system_cost_indices import update_system_cost_indices

__all__ = [
    "update_corporation_blueprints",
    "update_corporation_industry_jobs",
    "update_market_history",
    "update_market_histories",
    "update_market_orders",
    "update_markets_prices",
    "update_system_cost_indices",
]
