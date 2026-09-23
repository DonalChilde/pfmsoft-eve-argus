"""Data models for ESI responses used in the Argus application.

These models represent ESI data transformed into formats useful for the Argus application.

They are meant to be consumed by Argus functions, and possibly persisted in the Argus database.
"""

# TODO align this model collection with the other model collections, focus serialization
# and validation in wrapper classes, and use dataclasses for the data models themselves.

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Self

from pydantic import BaseModel, RootModel
from whenever import Instant


class EsiArgusBaseModel(BaseModel):
    """BaseModel class for ESI Argus models.

    This class is a wrapper for serialization and validation of ESI Argus model data.
    """

    # FIXME Because this is a serialization wrapper, the name should reflect that. Use
    # a different scheme to hold an full dataset so that it can be used independently of the wrapper.

    dataset: Any

    def serialize(self, indent: int | None = 2) -> str:
        """Serializes the ESI Argus model to a JSON string."""
        return self.model_dump_json(indent=indent)

    @classmethod
    def deserialize(cls, data: str) -> Self:
        """Deserializes a JSON string to an ESI Argus model."""
        return cls.model_validate_json(data)


@dataclass(slots=True, kw_only=True)
class EsiModelBase:
    """Base class for ESI sourced models."""

    received_at: str
    """The timestamp as an ISO 8601 string when the ESI data was fetched."""
    expires_at: str | None
    """The timestamp as an ISO 8601 string when the ESI data will expire, if provided by 
    the ESI response."""

    @property
    def expires_at_instant(self) -> Instant | None:
        """The timestamp when the ESI data will expire as an Instant, if available."""
        return Instant.parse_iso(self.expires_at) if self.expires_at else None

    @property
    def received_at_instant(self) -> Instant:
        """The timestamp when the ESI data was fetched as an Instant."""
        return Instant.parse_iso(self.received_at)

    def serialize(self, indent: int | None = 2) -> str:
        """Serializes the ESI model to a JSON string."""
        raise NotImplementedError("Subclasses must implement the serialize method.")

    @classmethod
    def deserialize(cls, data: str) -> Self:
        """Deserializes a JSON string to an ESI model."""
        raise NotImplementedError("Subclasses must implement the deserialize method.")


@dataclass(slots=True, kw_only=True)
class MarketGroup(EsiModelBase):
    """Argus model for market group details."""

    market_group_id: int
    name: str
    description: str
    parent_group_id: int | None = None
    types: list[int] = field(default_factory=list[int])
    path_str: tuple[str, ...] = field(default_factory=tuple[str])
    path_int: tuple[int, ...] = field(default_factory=tuple[int])

    def serialize(self, indent: int | None = 2) -> str:
        """Serializes the MarketGroup to a JSON string."""
        result = MarketGroupRoot(root=self).model_dump_json(indent=indent)
        return result

    @classmethod
    def deserialize(cls, data: str) -> MarketGroup:
        """Deserializes a JSON string to a MarketGroup model."""
        result = MarketGroupRoot.model_validate_json(data).root
        return result


class MarketGroupsDataset(EsiArgusBaseModel):
    """Argus model for a dataset of market groups."""

    dataset: dict[int, MarketGroup]


@dataclass(slots=True, kw_only=True)
class MarketOrderDetail:
    """Argus model for market order details."""

    duration: int
    is_buy_order: bool
    issued: str
    location_id: int
    min_volume: int
    order_id: int
    price: Decimal
    range: str
    system_id: int
    type_id: int
    volume_remain: int
    volume_total: int


@dataclass(slots=True, kw_only=True)
class DividedOrders:
    """Argus model for divided market orders."""

    buy_orders: list[MarketOrderDetail] = field(default_factory=list[MarketOrderDetail])
    sell_orders: list[MarketOrderDetail] = field(
        default_factory=list[MarketOrderDetail]
    )


@dataclass(slots=True, kw_only=True)
class RegionMarketOrders(EsiModelBase):
    """Argus model for market orders in a region."""

    region_id: int
    orders: dict[int, DividedOrders]  # type_id -> DividedOrders

    def serialize(self, indent: int | None = 2) -> str:
        """Serializes the RegionMarketOrders to a JSON string."""
        result = RegionMarketOrdersRoot(root=self).model_dump_json(indent=indent)
        return result

    @classmethod
    def deserialize(cls, data: str) -> RegionMarketOrders:
        """Deserializes a JSON string to a RegionMarketOrders model."""
        result = RegionMarketOrdersRoot.model_validate_json(data).root
        return result


RegionMarketOrdersRoot = RootModel[RegionMarketOrders]
MarketGroupRoot = RootModel[MarketGroup]


# -----------Market History Summary Models-----------


@dataclass(slots=True, kw_only=True)
class HistorySummary(EsiModelBase):
    """Represents an aggregate market-history summary for one region and item type.

    The summary covers a fixed window of consecutive days and stores the volume-weighted
    price averages for that window along with the average daily order count and volume.
    """

    region_id: int
    """The region ID associated with this summary."""
    type_id: int
    """The item type ID associated with this summary."""
    period: int
    """The number of days included in the summary window."""
    start: str
    """The end date of the window as an ISO date string in `YYYY-MM-DD` format."""
    end: str
    """The start date of the window as an ISO date string in `YYYY-MM-DD` format."""
    missing: int
    """The number of dates in the requested window that were missing from the source data."""
    highest: float
    """The volume-weighted average of the daily highest prices in the window."""
    average: float
    """The volume-weighted average of the daily average prices in the window."""
    lowest: float
    """The volume-weighted average of the daily lowest prices in the window."""
    order_count: int
    """The average daily order count across the selected window."""
    volume: float
    """The average daily traded volume across the selected window."""

    def serialize(self, indent: int | None = 2) -> str:
        """Serializes the HistorySummary to a JSON string."""
        return HistorySummaryRoot(root=self).model_dump_json(indent=indent)

    @classmethod
    def deserialize(cls, data: str) -> HistorySummary:
        """Deserializes a JSON string to a HistorySummary model."""
        result = HistorySummaryRoot.model_validate_json(data).root
        return result


HistorySummaryRoot = RootModel[HistorySummary]


@dataclass(slots=True, kw_only=True)
class RegionalHistorySummaries:
    """Represents the collection of market-history summaries for a region.

    Each summary covers a fixed window of consecutive days and stores the volume-weighted
    price averages for that window along with the average daily order count and volume.
    """

    region_id: int
    """The region ID associated with this collection of summaries."""
    summaries: dict[int, HistorySummary]
    """A mapping of item type IDs to their corresponding market-history summaries."""

    def serialize(self, indent: int | None = 2) -> str:
        """Serializes the RegionalHistorySummaries to a JSON string."""
        return RegionalHistorySummariesRoot(root=self).model_dump_json(indent=indent)

    @classmethod
    def deserialize(cls, data: str) -> RegionalHistorySummaries:
        """Deserializes a JSON string to a RegionalHistorySummaries model."""
        result = RegionalHistorySummariesRoot.model_validate_json(data).root
        return result


RegionalHistorySummariesRoot = RootModel[RegionalHistorySummaries]
