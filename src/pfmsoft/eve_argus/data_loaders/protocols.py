from collections.abc import Sequence
from typing import Protocol

from pfmsoft.eve_argus.models.esd import esd_argus, esd_datasets
from pfmsoft.eve_argus.models.esi import esi_argus, esi_response


class EsdDatasetsLoaderProtocol(Protocol):
    """Protocol for loading ESD datasets."""

    def blueprints(self) -> esd_datasets.BlueprintsDataset:
        """Returns the blueprints dataset loaded from ESD."""
        raise NotImplementedError("Subclasses must implement the blueprints method.")

    def type_materials(self) -> esd_datasets.TypeMaterialsDataset:
        """Returns the type materials dataset loaded from ESD."""
        raise NotImplementedError(
            "Subclasses must implement the type_materials method."
        )

    def types(self) -> esd_datasets.TypesDataset:
        """Returns the types dataset loaded from ESD."""
        raise NotImplementedError("Subclasses must implement the types method.")

    def meta_groups(self) -> esd_datasets.MetaGroupsDataset:
        """Returns the meta groups dataset loaded from ESD."""
        raise NotImplementedError("Subclasses must implement the meta_groups method.")

    def categories(self) -> esd_datasets.CategoriesDataset:
        """Returns the categories dataset loaded from ESD."""
        raise NotImplementedError("Subclasses must implement the categories method.")

    def groups(self) -> esd_datasets.GroupsDataset:
        """Returns the groups dataset loaded from ESD."""
        raise NotImplementedError("Subclasses must implement the groups method.")


class EsdArgusLoaderProtocol(Protocol):
    """Protocol for loading ESD Argus data."""

    pass


class EsiResponseLoaderProtocol(Protocol):
    """Protocol for loading ESI response data."""

    async def market_group_ids(self) -> esi_response.GetMarketsGroups:
        """Loads the market group IDs from ESI."""
        raise NotImplementedError(
            "Subclasses must implement the market_group_ids method."
        )

    async def market_groups_details(
        self, market_group_ids: Sequence[int]
    ) -> dict[int, esi_response.GetMarketsGroupsMarketGroupId]:
        """Loads the market group details from ESI."""
        raise NotImplementedError(
            "Subclasses must implement the market_group_details method."
        )

    async def region_market_orders(
        self, region_id: int
    ) -> esi_response.GetMarketsRegionIdOrders:
        """Loads the market orders for a region from ESI."""
        raise NotImplementedError(
            "Subclasses must implement the region_market_orders method."
        )

    async def region_market_histories(
        self, region_id: int, type_ids: set[int]
    ) -> dict[int, esi_response.GetMarketsRegionIdHistory]:
        """Loads the market history for a region and types from ESI."""
        raise NotImplementedError(
            "Subclasses must implement the region_market_history method."
        )

    async def markets_prices(self) -> esi_response.GetMarketsPrices:
        """Loads the market prices from ESI."""
        raise NotImplementedError(
            "Subclasses must implement the markets_prices method."
        )

    async def industry_systems(self) -> esi_response.GetIndustrySystems:
        """Loads the industry systems from ESI."""
        raise NotImplementedError(
            "Subclasses must implement the industry_systems method."
        )


class EsiArgusLoaderProtocol(Protocol):
    """Protocol for loading ESI Argus data."""

    def market_groups(
        self, market_group_ids: Sequence[int] | None = None
    ) -> dict[int, esi_argus.MarketGroup]:
        """Returns the market groups loaded from ESI Argus.

        Args:
            market_group_ids: Optional list of market group IDs to filter by. None means
                all market groups will be returned.

        Returns:
            A dictionary mapping market group IDs to MarketGroup objects.
        """
        raise NotImplementedError("Subclasses must implement the market_groups method.")

    def region_market_orders(self, region_id: int) -> esi_argus.RegionMarketOrders:
        """Returns the market orders for a region loaded from ESI Argus."""
        raise NotImplementedError(
            "Subclasses must implement the region_market_orders method."
        )
