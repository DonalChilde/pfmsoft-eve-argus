"""Protocols for data loaders in the EVE Argus project.

Protocols should define a method for each type of data that can be loaded, and the
expected return type for that method.
"""

from typing import Protocol
from uuid import UUID

from pfmsoft.eve_argus.models.esd import esd_datasets
from pfmsoft.eve_argus.models.esi import argus_response_models, esi_response_models


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

    async def market_group_ids(self) -> esi_response_models.GetMarketsGroupsResponse:
        """Loads the market group IDs from ESI."""
        raise NotImplementedError(
            "Subclasses must implement the market_group_ids method."
        )

    async def market_groups_details(
        self, market_group_ids: set[int]
    ) -> esi_response_models.GetMarketsGroupsMarketGroupIdCollectedResponse:
        """Loads the market group details from ESI."""
        raise NotImplementedError(
            "Subclasses must implement the market_group_details method."
        )

    async def region_market_orders(
        self, region_id: int
    ) -> esi_response_models.GetMarketsRegionIdOrdersResponse:
        """Loads the market orders for a region from ESI."""
        raise NotImplementedError(
            "Subclasses must implement the region_market_orders method."
        )

    async def region_market_histories(
        self, region_id: int, type_ids: set[int]
    ) -> esi_response_models.GetMarketsRegionIdHistoryCollectedResponse:
        """Loads the market history for a region and types from ESI."""
        raise NotImplementedError(
            "Subclasses must implement the region_market_history method."
        )

    async def markets_prices(self) -> esi_response_models.GetMarketsPricesResponse:
        """Loads the market prices from ESI."""
        raise NotImplementedError(
            "Subclasses must implement the markets_prices method."
        )

    async def industry_systems(self) -> esi_response_models.GetIndustrySystemsResponse:
        """Loads the industry systems from ESI."""
        raise NotImplementedError(
            "Subclasses must implement the industry_systems method."
        )

    async def universe_names(
        self, ids: set[int]
    ) -> esi_response_models.PostUniverseNamesResponse:
        """Loads the universe names for a set of IDs from ESI."""
        raise NotImplementedError(
            "Subclasses must implement the universe_names method."
        )

    async def universe_type_ids(self) -> esi_response_models.GetUniverseTypesResponse:
        """Loads the universe type IDs from ESI."""
        raise NotImplementedError(
            "Subclasses must implement the universe_type_ids method."
        )

    async def corporation_industry_jobs(
        self, corporation_id: int, character_id: int, credential_id: UUID
    ) -> esi_response_models.GetCorporationsCorporationIdIndustryJobsResponse:
        """Loads the industry jobs for a corporation from ESI."""
        raise NotImplementedError(
            "Subclasses must implement the corporation_industry_jobs method."
        )


class EsiArgusLoaderProtocol(Protocol):
    """Protocol for loading ESI Argus data."""

    def market_groups(
        self, market_group_ids: set[int] | None = None
    ) -> dict[int, argus_response_models.MarketGroup]:
        """Returns the market groups loaded from ESI Argus.

        Args:
            market_group_ids: Optional list of market group IDs to filter by. None means
                all market groups will be returned.

        Returns:
            A dictionary mapping market group IDs to MarketGroup objects.
        """
        raise NotImplementedError("Subclasses must implement the market_groups method.")

    def region_market_orders(
        self, region_id: int
    ) -> argus_response_models.RegionMarketOrders:
        """Returns the market orders for a region loaded from ESI Argus."""
        raise NotImplementedError(
            "Subclasses must implement the region_market_orders method."
        )

    def region_market_histories(
        self, region_id: int, type_ids: set[int]
    ) -> argus_response_models.RegionalHistorySummaries:
        """Returns the market histories for a region and types loaded from ESI Argus."""
        raise NotImplementedError(
            "Subclasses must implement the region_market_histories method."
        )
