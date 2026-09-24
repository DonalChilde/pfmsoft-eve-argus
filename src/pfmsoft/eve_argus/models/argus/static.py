"""Models related to the argus static data db."""

from dataclasses import dataclass

from pydantic import RootModel

from pfmsoft.eve_argus.models.common import Serializable


@dataclass(slots=True, kw_only=True)
class IndustryActivityRecord:
    activity_id: int
    name: str
    description: str


IndustryActivityDataset = dict[int, IndustryActivityRecord]
IndustryActivityDatasetRoot = RootModel[IndustryActivityDataset]


@dataclass(slots=True, kw_only=True)
class MarketGroupRecord:
    market_group_id: int
    name: str
    description: str
    parent_group_id: int | None
    has_types: bool
    icon_id: int | None
    int_path: tuple[int, ...]
    str_path: tuple[str, ...]
    types: tuple[int, ...]


MarketGroupDataset = dict[int, MarketGroupRecord]
MarketGroupDatasetRoot = RootModel[MarketGroupDataset]
