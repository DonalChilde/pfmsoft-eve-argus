from collections.abc import Sequence
from typing import Protocol

from pfmsoft.eve_argus.models.esd import esd_argus, esd_datasets
from pfmsoft.eve_argus.models.esi import esi_argus, esi_response


class EsdDatasetsLoaderProtocol(Protocol):
    """Protocol for loading ESD datasets."""

    pass


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

    async def market_group_details(
        self, market_group_id: Sequence[int]
    ) -> esi_response.GetMarketsGroupsMarketGroupId:
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
