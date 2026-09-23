"""Eve Argus public interface."""

import logging
import sqlite3
from time import perf_counter_ns
from types import TracebackType
from typing import Self

from pfmsoft.eve_link import EsiLink, EsiSchema, SimpleRequests
from pfmsoft.eve_sd import EveSdDbQueryManager
from pfmsoft.eve_snippets.sqlite3.connection_helpers import create_read_write_connection

from pfmsoft.eve_argus.market.orders.db.query_helpers import (
    load_table_definitions as load_order_table_definitions,
)
from pfmsoft.eve_argus.settings import EveArgusSettings
from pfmsoft.eve_argus.static.db.query_helpers import (
    load_table_definitions as load_argus_static_table_definitions,
)

logger = logging.getLogger(__name__)


class EveArgusResources:
    def __init__(self, settings: EveArgusSettings) -> None:
        """Initialize the EveArgus instance."""
        self._settings = settings
        self._simple_requests = SimpleRequests(settings=settings.eve_link_settings)
        self._esi_link: EsiLink | None = None
        self._sd_query_manager: EveSdDbQueryManager | None = None
        self._esi_schema: EsiSchema | None = None
        self._order_db_connection: sqlite3.Connection | None = None
        self._argus_static_db_connection: sqlite3.Connection | None = None

    async def __aenter__(self) -> Self:
        """Enter the async context manager."""
        logger.info("Acquiring EveArgus resources")
        start = perf_counter_ns()
        self._esi_link = self._simple_requests.esi_link_factory()
        self._esi_schema = self._simple_requests.get_schema(
            compatibility_date=self._settings.compatibility_date
        )
        await self._esi_link.__aenter__()
        self._sd_query_manager = EveSdDbQueryManager(self._settings.static_database)
        self._sd_query_manager.__enter__()
        self._order_db_connection = create_read_write_connection(
            self._settings.market_orders_database, load_order_table_definitions()
        )
        self._argus_static_db_connection = create_read_write_connection(
            self._settings.static_database, load_argus_static_table_definitions()
        )
        end = perf_counter_ns()
        seconds = f"{(end - start) / 1_000_000_000:.6f} s"
        logger.info("Acquired EveArgus resources in %s", seconds)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit the async context manager."""
        if self._esi_link is not None:
            await self._esi_link.__aexit__(exc_type, exc_value, traceback)
            self._esi_link = None
        if self._sd_query_manager is not None:
            self._sd_query_manager.__exit__(exc_type, exc_value, traceback)
            self._sd_query_manager = None
        if self._order_db_connection is not None:
            self._order_db_connection.close()
            self._order_db_connection = None
        if self._argus_static_db_connection is not None:
            self._argus_static_db_connection.close()
            self._argus_static_db_connection = None
        if self._esi_schema is not None:
            self._esi_schema = None

    @property
    def esi_link(self) -> EsiLink:
        """Get the EsiLink instance."""
        if self._esi_link is None:
            raise RuntimeError(
                "EveArgusResources is not initialized. Use 'async with' to initialize."
            )
        return self._esi_link

    @property
    def sd_query_manager(self) -> EveSdDbQueryManager:
        """Get the EveSdDbQueryManager instance."""
        if self._sd_query_manager is None:
            raise RuntimeError(
                "EveArgusResources is not initialized. Use 'async with' to initialize."
            )
        return self._sd_query_manager

    @property
    def esi_schema(self) -> EsiSchema:
        """Get the EsiSchema instance."""
        if self._esi_schema is None:
            raise RuntimeError(
                "EveArgusResources is not initialized. Use 'async with' to initialize."
            )
        return self._esi_schema

    @property
    def order_db_connection(self) -> sqlite3.Connection:
        """Get the order database connection."""
        if self._order_db_connection is None:
            raise RuntimeError(
                "EveArgusResources is not initialized. Use 'async with' to initialize."
            )
        return self._order_db_connection


__all__ = ["EveArgusResources"]
