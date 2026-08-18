"""Eve Argus public interface."""

from types import TracebackType
from typing import Self

from pfmsoft.eve_link import EsiLink, EsiSchema, SimpleRequests
from pfmsoft.eve_sd import EveSdDbQueryManager

from pfmsoft.eve_argus.settings import EveArgusSettings


class EveArgusResources:
    def __init__(self, settings: EveArgusSettings) -> None:
        """Initialize the EveArgus instance."""
        self._settings = settings
        self._simple_requests = SimpleRequests(settings=settings.eve_link_settings)
        self._esi_link: EsiLink | None = None
        self._sd_query_manager: EveSdDbQueryManager | None = None
        self._esi_schema: EsiSchema | None = None

    async def __aenter__(self) -> Self:
        """Enter the async context manager."""
        self._esi_link = self._simple_requests.esi_link_factory()
        self._esi_schema = self._simple_requests.get_schema(
            compatibility_date=self._settings.compatibility_date
        )
        await self._esi_link.__aenter__()
        self._sd_query_manager = EveSdDbQueryManager(self._settings.static_database)
        self._sd_query_manager.__enter__()
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


__all__ = ["EveArgusResources"]
