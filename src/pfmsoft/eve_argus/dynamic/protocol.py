"""Dynamic DB protocols."""

from sqlite3 import Connection
from typing import Protocol

from pfmsoft.eve_argus.dynamic.db import models as ADM
from pfmsoft.eve_argus.models.esi import esi_response_models as ERM


class DynamicDBWriteProtocol(Protocol):
    def write_markets_prices(
        self, connection: Connection, *, markets_prices: ERM.GetMarketsPrices
    ) -> None:
        """Write market prices."""
        ...

    def write_market_orders(
        self, connection: Connection, *, market_orders: ERM.GetMarketsRegionIdOrders
    ) -> None:
        """Write market orders."""
        ...

    def write_order_summaries(
        self, connection: Connection, *, order_summaries: ADM.OrderSummaryDataset
    ) -> None:
        """Write order summaries."""
        ...

    def write_system_cost_indices(
        self, connection: Connection, *, system_cost_indices: ERM.GetIndustrySystems
    ) -> None:
        """Write system cost indices."""
        ...

    def write_corporation_industry_jobs(
        self,
        connection: Connection,
        *,
        jobs: ERM.GetCorporationsCorporationIdIndustryJobs,
    ) -> None:
        """Write corporation industry jobs."""
        ...

    def write_corporation_blueprints(
        self,
        connection: Connection,
        *,
        blueprints: ERM.GetCorporationsCorporationIdBlueprints,
    ) -> None:
        """Write corporation blueprints."""
        ...


class DynamicDBReadProtocol(Protocol):
    def read_markets_prices(
        self, connection: Connection, *, response_metadata_id: int
    ) -> ADM.MarketsPricesDataset:
        """Read market prices."""
        ...

    def read_markets_prices_responses(
        self, connection: Connection
    ) -> list[ADM.MarketsPricesResponse]:
        """Read market prices responses.

        Returns:
            list of responses ordered by received_at timestamp
        """
        ...

    def read_market_orders(
        self, connection: Connection, *, response_metadata_id: int
    ) -> ADM.MarketOrdersDataset:
        """Read market orders."""
        ...

    def read_market_orders_responses(
        self, connection: Connection, *, region_id: int | None
    ) -> list[ADM.MarketOrdersResponse]:
        """Read market orders responses.

        Args:
            connection: the DB connection
            region_id: filter by region if given. None means all regions.

        Returns:
            list of responses ordered by received_at timestamp
        """
        ...

    def read_order_summaries(
        self, connection: Connection, *, order_summary_response_id: int
    ) -> ADM.OrderSummaryDataset:
        """Read order summaries."""
        ...

    def read_order_summaries_responses(
        self, connection: Connection, *, region_id: int | None
    ) -> list[ADM.OrderSummaryResponse]:
        """Read order summaries responses.

        Args:
            connection: the DB connection
            region_id: filter by region if given. None means all regions.

        Returns:
            list of responses ordered by received_at timestamp
        """
        ...

    def read_system_cost_indices(
        self, connection: Connection, *, response_metadata_id: int
    ) -> ADM.SystemCostIndicesDataset:
        """Read system cost indices."""
        ...

    def read_system_cost_indices_responses(
        self, connection: Connection
    ) -> list[ADM.SystemCostIndicesResponse]:
        """Read system cost indices responses.

        Returns:
            list of responses ordered by received_at timestamp.
        """
        ...

    def read_corporation_industry_jobs(
        self, connection: Connection, *, response_metadata_id: int
    ) -> ADM.CorporationIndustryJobsDataset:
        """Read corporation industry jobs."""
        ...

    def read_corporation_industry_jobs_responses(
        self, connection: Connection, *, corporation_id: int | None
    ) -> list[ADM.CorporationIndustryJobsResponse]:
        """Read corporation industry jobs responses.

        Args:
            connection: the DB connection
            corporation_id: filter by corporation if given.

        Returns:
            list of responses ordered by received_at timestamp.
        """
        ...

    def read_corporation_blueprints(
        self, connection: Connection, *, response_metadata_id: int
    ) -> ADM.CorporationBlueprintsDataset:
        """Read corporation blueprints."""
        ...

    def read_corporation_blueprints_responses(
        self, connection: Connection, *, corporation_id: int | None
    ) -> list[ADM.CorporationBlueprintsResponse]:
        """Read corporation blueprints responses.

        Args:
            connection: the DB connection
            corporation_id: filter by corporation if given.

        Returns:
            list of responses ordered by received_at timestamp.
        """
        ...


# TODO implement other delete methods
class DynamicDBDeleteProtocol(Protocol):
    def delete_market_orders(
        self, connection: Connection, *, response_metadata_id: int
    ) -> None:
        """Delete market orders."""
        ...


# TODO implement other util methods
class DynamicDBUtilProtocol(Protocol): ...
