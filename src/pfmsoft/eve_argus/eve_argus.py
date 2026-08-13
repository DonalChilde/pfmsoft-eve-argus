from types import TracebackType
from typing import Self

from pfmsoft.eve_link import EsiLink
from pfmsoft.eve_sd.db.query import DatasetDbQuery

from pfmsoft.eve_argus.settings import EveArgusSettings


class EveArgus:
    def __init__(self, settings: EveArgusSettings) -> None:
        self.settings = settings

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        pass
