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
