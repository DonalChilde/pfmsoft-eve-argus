"""Eve Argus public interface."""

from types import TracebackType
from typing import Self

from pfmsoft.eve_link import EsiLink
from pfmsoft.eve_sd import EveSdDbQueryManager

from pfmsoft.eve_argus.settings import EveArgusSettings


class EveArgusResources:
    def __init__(self, settings: EveArgusSettings) -> None:
        """Initialize the EveArgus instance."""
        self._settings = settings
        self._esi_link: EsiLink | None = None
        self._sd_query_manager: EveSdDbQueryManager | None = None

    async def __aenter__(self) -> Self:
        """Enter the async context manager."""
        self._esi_link = EsiLink.from_settings(self._settings.eve_link_settings)
        await self._esi_link.__aenter__()
        self._sd_query_manager = EveSdDbQueryManager(self._settings.static_database)
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
