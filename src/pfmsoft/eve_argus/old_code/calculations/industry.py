"""Module for industry-related calculations."""

from eve_static_data.models import yaml_records as YR
from eve_static_data.models.common import Lang

from esi_link.argus.models.esi_models import GetIndustrySystems, GetMarketsPrices


class BillOfMaterials:
    """Represents the bill of materials for a given item type ID.

    Contains the required materials and their quantities needed to produce one unit of the item.
    Includes BOM for sub assemblies.
    """

    pass


class IndustryCalculator:
    def __init__(
        self,
        blueprints: dict[int, YR.Blueprints],
        cost_indices: GetIndustrySystems,
        universe_pricing: GetMarketsPrices,
    ):
        self.blueprints = blueprints
        self.cost_indices = cost_indices
        self.universe_pricing = universe_pricing

    def bill_of_materials(self, type_id: int) -> BillOfMaterials | None:
        """Calculate the bill of materials for a given item type ID.

        if the item cannot be produced from a blueprint, returns None.
        """
        # TODO stub
        return None

    def estimated_item_value(self, type_id: int) -> float | None:
        """Calculate the estimated value of an item based on its bill of materials and current market prices.

        if the item cannot be produced from a blueprint, returns None.
        """
        # TODO stub
        return None

    def process_time_value(self, type_id: int) -> float | None:
        """Calculate the estimated processing time value for an item based on its bill of materials and current market prices.

        Needs more research and documentation, probably needs a starting value and and ending value.
        eg, me research from 3 to 10.

        if the item cannot be produced from a blueprint, returns None.
        """
        # TODO stub
        return None
