"""Data models for ESI responses used in the Argus application.

These models represent ESI data transformed into formats useful for the Argus application.

They are meant to be consumed by Argus functions, and possibly persisted in the Argus database.
"""

# TODO align this model collection with the other model collections, focus serialization
# and validation in wrapper classes, and use dataclasses for the data models themselves.

from dataclasses import dataclass, field
from typing import Any, Self

from pydantic import BaseModel, RootModel
from whenever import Instant


class EsiArgusBaseModel(BaseModel):
    """BaseModel class for ESI Argus models.

    This class is a wrapper for serialization and validation of ESI Argus model data.
    """

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
    price: float
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


# --------Order Summary Models--------
@dataclass(slots=True, kw_only=True)
class OrderSummaryItem:
    """Represents one side of the market depth for a single item type.

    This summary is built from the valid orders after outlier filtering. The 5% depth
    metrics describe the best-price threshold needed to reach 5% of the filtered volume.
    """

    type_id: int
    """The item type ID represented by this summary."""
    is_buy_summary: bool
    """True when this summary describes buy orders; False for sell orders."""
    five_price: float
    """The price of the last order included in the 5% cumulative-volume threshold."""
    five_orders: int
    """The number of orders needed to reach the 5% cumulative-volume target."""
    five_items: int
    """The total volume available at or better than ``five_price`` in the threshold bucket."""
    lowest: float
    """The lowest valid order price after outlier filtering."""
    highest: float
    """The highest valid order price after outlier filtering."""
    total_items: int
    """The total valid volume remaining after outlier filtering."""
    total_orders: int
    """The count of valid orders remaining after outlier filtering."""
    avg_price: float
    """The volume-weighted average price of the valid orders."""
    filtered_items: int
    """The volume removed by the outlier filter."""
    filtered_orders: int
    """The number of orders removed by the outlier filter."""


@dataclass(slots=True, kw_only=True)
class OrderSummary:
    """Represents the buy and sell summary for one item type in a region.

    The summary may be scoped to a single solar system or location instead of the whole
    region.
    """

    region_id: int
    solar_system_id: int | None
    location_id: int | None
    type_id: int
    buy_summary: OrderSummaryItem
    sell_summary: OrderSummaryItem


@dataclass(slots=True, kw_only=True)
class OrderSummaries(EsiModelBase):
    """Represents the collection of order summaries for a region.

    The collection may be limited to a specific solar system or location and uses a shared
    outlier filter factor for all item summaries.
    """

    region_id: int
    solar_system_id: int | None
    location_id: int | None
    filter_factor: float
    summaries: dict[int, OrderSummary]

    def serialize(self, indent: int | None = 2) -> str:
        """Serializes the OrderSummaries to a JSON string."""
        return OrderSummariesRoot(root=self).model_dump_json(indent=indent)

    @classmethod
    def deserialize(cls, data: str) -> OrderSummaries:
        """Deserializes a JSON string to an OrderSummaries model."""
        result = OrderSummariesRoot.model_validate_json(data).root
        return result


OrderSummariesRoot = RootModel[OrderSummaries]


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
