"""Dynamic DB access."""

from sqlite3 import Connection

from pfmsoft.eve_argus.dynamic.db import models as ADM
from pfmsoft.eve_argus.dynamic.db import query_helpers as QH
from pfmsoft.eve_argus.dynamic.protocol import (
    DynamicDBReadProtocol,
    DynamicDBWriteProtocol,
)
from pfmsoft.eve_argus.models.esi import esi_response_models as ERM


class DynamicDBWriter(DynamicDBWriteProtocol):
    def write_markets_prices(
        self, connection: Connection, *, markets_prices: ERM.GetMarketsPrices
    ) -> None:
        """Write market prices."""
        QH.write_markets_prices(connection, markets_prices=markets_prices)

    def write_market_orders(
        self, connection: Connection, *, market_orders: ERM.GetMarketsRegionIdOrders
    ) -> None:
        """Write market orders."""
        QH.write_market_orders(connection, market_orders=market_orders)

    def write_order_summaries(
        self, connection: Connection, *, order_summaries: ADM.OrderSummaryDataset
    ) -> None:
        """Write order summaries."""
        QH.write_order_summaries(connection, order_summaries=order_summaries)

    def write_system_cost_indices(
        self, connection: Connection, *, system_cost_indices: ERM.GetIndustrySystems
    ) -> None:
        """Write system cost indices."""
        QH.write_system_cost_indices(
            connection, system_cost_indices=system_cost_indices
        )

    def write_corporation_industry_jobs(
        self,
        connection: Connection,
        *,
        jobs: ERM.GetCorporationsCorporationIdIndustryJobs,
    ) -> None:
        """Write corporation industry jobs."""
        QH.write_corporation_industry_jobs(connection, jobs=jobs)

    def write_corporation_blueprints(
        self,
        connection: Connection,
        *,
        blueprints: ERM.GetCorporationsCorporationIdBlueprints,
    ) -> None:
        """Write corporation blueprints."""
        QH.write_corporation_blueprints(connection, blueprints=blueprints)


class DynamicDBReader(DynamicDBReadProtocol):
    def read_markets_prices(
        self, connection: Connection, *, response_metadata_id: int
    ) -> ADM.MarketsPricesDataset:
        """Read market prices."""
        return QH.get_markets_prices(
            connection, response_metadata_id=response_metadata_id
        )

    def read_markets_prices_responses(
        self, connection: Connection
    ) -> list[ADM.MarketsPricesResponse]:
        """Read market prices responses."""
        return QH.get_markets_prices_responses(connection)

    def read_market_orders(
        self, connection: Connection, *, response_metadata_id: int
    ) -> ADM.MarketOrdersDataset:
        """Read market orders."""
        return QH.get_market_orders(
            connection, response_metadata_id=response_metadata_id
        )

    def read_market_orders_responses(
        self, connection: Connection, *, region_id: int | None
    ) -> list[ADM.MarketOrdersResponse]:
        """Read market orders responses."""
        return QH.get_market_orders_responses(connection, region_id=region_id)

    def read_order_summaries(
        self, connection: Connection, *, order_summary_response_id: int
    ) -> ADM.OrderSummaryDataset:
        """Read order summaries."""
        return QH.get_order_summaries(
            connection, order_summary_response_id=order_summary_response_id
        )

    def read_order_summaries_responses(
        self, connection: Connection, *, region_id: int | None
    ) -> list[ADM.OrderSummaryResponse]:
        """Read order summaries responses."""
        return QH.get_order_summary_responses(connection, region_id=region_id)

    def read_system_cost_indices(
        self, connection: Connection, *, response_metadata_id: int
    ) -> ADM.SystemCostIndicesDataset:
        """Read system cost indices."""
        return QH.get_system_cost_indices(
            connection, response_metadata_id=response_metadata_id
        )

    def read_system_cost_indices_responses(
        self, connection: Connection
    ) -> list[ADM.SystemCostIndicesResponse]:
        """Read system cost indices responses."""
        return QH.get_system_cost_indices_responses(connection)

    def read_corporation_industry_jobs(
        self, connection: Connection, *, response_metadata_id: int
    ) -> ADM.CorporationIndustryJobsDataset:
        """Read corporation industry jobs."""
        return QH.get_corporation_industry_jobs(
            connection, response_metadata_id=response_metadata_id
        )

    def read_corporation_industry_jobs_responses(
        self, connection: Connection, *, corporation_id: int | None
    ) -> list[ADM.CorporationIndustryJobsResponse]:
        """Read corporation industry jobs responses."""
        return QH.get_corporation_industry_jobs_responses(
            connection, corporation_id=corporation_id
        )

    def read_corporation_blueprints(
        self, connection: Connection, *, response_metadata_id: int
    ) -> ADM.CorporationBlueprintsDataset:
        """Read corporation blueprints."""
        return QH.get_corporation_blueprints(
            connection, response_metadata_id=response_metadata_id
        )

    def read_corporation_blueprints_responses(
        self, connection: Connection, *, corporation_id: int | None
    ) -> list[ADM.CorporationBlueprintsResponse]:
        """Read corporation blueprints responses."""
        return QH.get_corporation_blueprints_responses(
            connection, corporation_id=corporation_id
        )
