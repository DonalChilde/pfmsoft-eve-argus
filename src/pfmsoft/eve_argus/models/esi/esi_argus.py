"""Data models for ESI responses used in the Argus application.

These models represent ESI data transformed into formats useful for the Argus application.

They are meant to be consumed by Argus functions, and possibly persisted in the Argus database.
"""

from dataclasses import dataclass, field
from typing import Self

from pydantic import RootModel
from whenever import Instant


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
