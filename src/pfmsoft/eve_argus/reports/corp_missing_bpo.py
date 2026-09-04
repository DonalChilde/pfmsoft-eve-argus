# Collect necessary data to identify missing BPO blueprints in the corporation's inventory.
# A BPO blueprint is considered missing if it is avaliable on the market but not in the corporation's inventory.
# The report should be able to list all owned blueprints,with market path string, quantity for each, and the Highest ME/TE available in an "owned" table.
# The missing table should list all BPO blueprints that are available on the market but not owned by the corporation, including their market path string and base price.
# only published blueprints should be considered.

from pfmsoft.eve_argus.data_loaders.esi_responses import EsiResponseLoader
from pfmsoft.eve_argus.data_loaders.protocols import EsdDatasetsLoaderProtocol
from pfmsoft.eve_argus.helpers.market_path_filters import filter_type_ids_by_market_path

BLUEPRINTS_MARKET_GROUP = 2
