"""Access classes for market history."""

from sqlite3 import Connection

from pfmsoft.eve_argus.market.history.db import models
from pfmsoft.eve_argus.market.history.db import query_helpers as QH
from pfmsoft.eve_argus.market.history.protocol import (
    MarketHistoryReadProtocol,
    MarketHistoryWriteProtocol,
)
from pfmsoft.eve_argus.models.esi import esi_response_models as ERM


class MarketHistoryReader(MarketHistoryReadProtocol):
    def read_market_history_responses(
        self, connection: Connection, region_id: int, type_id: int
    ) -> tuple[models.MarketHistoryResponse, ...]:
        """Read response metadata for a region and type.

        Shows a list of responses for the region and type. Each response represents
        an update call to the Eve ESI.

        Args:
            connection: Database connection.
            region_id: Region ID.
            type_id: Type ID.

        Returns:
            Response metadata ordered by received time descending.
        """
        return QH.read_market_history_responses(
            connection, region_id=region_id, type_id=type_id
        )

    def read_market_history(
        self, connection: Connection, region_id: int, type_id: int
    ) -> tuple[models.MarketHistoryRecord, ...]:
        """Read all market history for a region and type.

        Args:
            connection: Database connection.
            region_id: Region ID.
            type_id: Type ID.

        Returns:
            Market history records ordered by date descending.
        """
        return QH.read_market_history(connection, region_id=region_id, type_id=type_id)

    def read_market_history_date_range(
        self,
        connection: Connection,
        region_id: int,
        type_id: int,
        start: str | None,
        end: str | None,
    ) -> tuple[models.MarketHistoryRecord, ...]:
        """Read market history between date bounds, ordered newest first.

        Args:
            connection: Database connection.
            region_id: Region ID for the market history.
            type_id: Type ID for the market history.
            start: Inclusive ISO date bound for the most recent date, or None to
                start at the beginning of available history.
            end: Inclusive ISO date bound for the oldest date, or None to continue
                through the end of available history.

        Returns:
            Market history records ordered by date descending, most recent first.
        """
        return QH.read_market_history_date_range(
            connection, region_id=region_id, type_id=type_id, start=start, end=end
        )

    def read_market_history_latest(
        self, connection: Connection, region_id: int, type_id: int, count: int
    ) -> tuple[models.MarketHistoryRecord, ...]:
        """Read the latest market history records.

        Args:
            connection: Database connection.
            region_id: Region ID.
            type_id: Type ID.
            count: Number of records to fetch. Must be > 0.

        Returns:
            Latest market history records ordered by date descending.

        Raises:
            ValueError: If count is negative or zero.
        """
        return QH.read_market_history_latest(
            connection, region_id=region_id, type_id=type_id, count=count
        )


class MarketHistoryWrite(MarketHistoryWriteProtocol):
    def write_market_history(
        self, connection: Connection, history: ERM.GetMarketsRegionIdHistory
    ) -> None:
        """Write market history data to the database.

        Also writes the response metadata.

        Args:
            connection: Database connection.
            history: Market history data.
        """
        return QH.write_market_history(connection, history=history)
