"""Eve Argus public interface."""

import logging
import sqlite3
from time import perf_counter_ns
from types import TracebackType
from typing import Self

from pfmsoft.eve_link import EsiLink, EsiSchema, SimpleRequests

from pfmsoft.eve_argus.dynamic.util import (
    load_table_definitions as load_argus_dynamic_table_definitions,
)
from pfmsoft.eve_argus.helpers.connection_helpers import create_read_write_connection
from pfmsoft.eve_argus.market_history.util import (
    load_table_definitions as load_history_table_definitions,
)
from pfmsoft.eve_argus.settings import EveArgusSettings
from pfmsoft.eve_argus.static.store import StaticStore

logger = logging.getLogger(__name__)


class EveArgusResources:
    def __init__(self, settings: EveArgusSettings) -> None:
        """Initialize the EveArgus instance."""
        self._settings = settings
        self._simple_requests = SimpleRequests(settings=settings.eve_link_settings)
        self._esi_link: EsiLink | None = None
        self._esi_schema: EsiSchema | None = None
        self._argus_static_db_connection: sqlite3.Connection | None = None
        self._argus_dynamic_db_connection: sqlite3.Connection | None = None
        self._history_db_connection: sqlite3.Connection | None = None

    async def __aenter__(self) -> Self:
        """Enter the async context manager."""
        logger.info("Acquiring EveArgus resources")
        start = perf_counter_ns()
        self._esi_link = self._simple_requests.esi_link_factory()
        self._esi_schema = self._simple_requests.get_schema(
            compatibility_date=self._settings.compatibility_date
        )
        await self._esi_link.__aenter__()
        static_store = StaticStore(store_path=self._settings.static_database_store)
        static_db_path = static_store.get_file_path_for_entry(
            build_number=self._settings.static_database_build_number
        )
        # The store manager should ensure that the static database file exists before attempting to connect.
        self._argus_static_db_connection = create_read_write_connection(static_db_path)
        self._argus_dynamic_db_connection = create_read_write_connection(
            self._settings.argus_dynamic_database,
            init_sql=load_argus_dynamic_table_definitions(),
        )
        self._history_db_connection = create_read_write_connection(
            self._settings.market_history_database,
            init_sql=load_history_table_definitions(),
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
        if self._argus_static_db_connection is not None:
            self._argus_static_db_connection.close()
            self._argus_static_db_connection = None
        if self._argus_dynamic_db_connection is not None:
            self._argus_dynamic_db_connection.close()
            self._argus_dynamic_db_connection = None
        if self._history_db_connection is not None:
            self._history_db_connection.close()
            self._history_db_connection = None
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
    def esi_schema(self) -> EsiSchema:
        """Get the EsiSchema instance."""
        if self._esi_schema is None:
            raise RuntimeError(
                "EveArgusResources is not initialized. Use 'async with' to initialize."
            )
        return self._esi_schema

    @property
    def argus_static_db_connection(self) -> sqlite3.Connection:
        """Get the Argus static database connection."""
        if self._argus_static_db_connection is None:
            raise RuntimeError(
                "EveArgusResources is not initialized. Use 'async with' to initialize."
            )
        return self._argus_static_db_connection

    @property
    def argus_dynamic_db_connection(self) -> sqlite3.Connection:
        """Get the Argus dynamic database connection."""
        if self._argus_dynamic_db_connection is None:
            raise RuntimeError(
                "EveArgusResources is not initialized. Use 'async with' to initialize."
            )
        return self._argus_dynamic_db_connection

    @property
    def market_history_db_connection(self) -> sqlite3.Connection:
        """Get the market history database connection."""
        if self._history_db_connection is None:
            raise RuntimeError(
                "EveArgusResources is not initialized. Use 'async with' to initialize."
            )
        return self._history_db_connection


__all__ = ["EveArgusResources"]
