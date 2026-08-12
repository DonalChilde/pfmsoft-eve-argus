"""Data models for ESI responses used in the Argus application.

These models are designed to represent the structure of the data returned by the
EVE Swagger Interface (ESI) API. They provide a structured way to handle and manipulate
the data received from ESI, and include the response data with enough request data to
fully define the dataset.

The EsiResponseBase class serves as a base class for all ESI response models, providing
common attributes such as received_at and expires_at timestamps.

Models are named according to the ESI endpoint (operation ID) they represent.

Where the response data is a collection of complex type items, the individual items are
represented by a separate data class, suffixed with `Detail`, which is used as a type
for the collection of items in the response model.
"""

from dataclasses import dataclass
from typing import Self

from pydantic import RootModel
from whenever import Instant


@dataclass(slots=True, kw_only=True)
class EsiResponseBase:
    """Base class for ESI response models."""

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
        """Serializes the ESI response model to a JSON string."""
        raise NotImplementedError("Subclasses must implement the serialize method.")

    @classmethod
    def deserialize(cls, data: str) -> Self:
        """Deserializes a JSON string to an ESI response model."""
        raise NotImplementedError("Subclasses must implement the deserialize method.")


@dataclass(slots=True, kw_only=True)
class GetMarketsRegionIdOrdersDetail:
    """Detail for market orders response."""

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
class GetMarketsRegionIdOrders(EsiResponseBase):
    """Response model for market orders."""

    region_id: int
    """The region ID for which the market orders were fetched."""
    orders: list[GetMarketsRegionIdOrdersDetail]

    def serialize(self, indent: int | None = 2) -> str:
        """Serializes the GetMarketsRegionIdOrders to a JSON string."""
        return GetMarketsRegionIdOrdersRoot(root=self).model_dump_json(
            indent=indent,
        )

    @classmethod
    def deserialize(cls, data: str) -> GetMarketsRegionIdOrders:
        """Deserializes a JSON string to a GetMarketsRegionIdOrders model."""
        result = GetMarketsRegionIdOrdersRoot.model_validate_json(data).root
        return result


GetMarketsRegionIdOrdersRoot = RootModel[GetMarketsRegionIdOrders]
