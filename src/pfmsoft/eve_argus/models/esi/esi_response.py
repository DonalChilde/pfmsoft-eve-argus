"""Data models for ESI responses used in the Argus application.

These models are designed to represent the structure of the data returned by the
EVE Swagger Interface (ESI) API. They provide a structured way to handle and manipulate
the data received from ESI, and include the response data with enough request data to
fully define the dataset.

They are expected to be transformed into Argus specific models for use in the Argus
application.

The EsiResponseBase class serves as a base class for all ESI response models, providing
common attributes such as received_at and expires_at timestamps.

Models are named according to the ESI endpoint (operation ID) they represent.

Where the response data is a collection of complex type items, the individual items are
represented by a separate data class, suffixed with `Detail`, which is used as a type
for the collection of items in the response model.
"""

from dataclasses import dataclass, field
from enum import StrEnum
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


GetMarketsRegionIdOrdersDetailRoot = RootModel[GetMarketsRegionIdOrdersDetail]


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


@dataclass(slots=True, kw_only=True)
class GetMarketsGroups(EsiResponseBase):
    """Response model for market groups."""

    group_ids: list[int]

    def serialize(self, indent: int | None = 2) -> str:
        """Serializes the GetMarketsGroups to a JSON string."""
        return GetMarketsGroupsRoot(root=self).model_dump_json(
            indent=indent,
        )

    @classmethod
    def deserialize(cls, data: str) -> GetMarketsGroups:
        """Deserializes a JSON string to a GetMarketsGroups model."""
        result = GetMarketsGroupsRoot.model_validate_json(data).root
        return result


@dataclass(slots=True, kw_only=True)
class GetMarketsGroupsMarketGroupIdDetail:
    """Response model for market group details."""

    market_group_id: int
    """The market group ID for which the details were fetched."""
    name: str
    description: str
    parent_group_id: int | None = None
    types: list[int] = field(default_factory=list[int])

    def serialize(self, indent: int | None = 2) -> str:
        """Serializes the GetMarketsGroupsMarketGroupIdDetail to a JSON string."""
        return GetMarketsGroupsMarketGroupIdDetailRoot(root=self).model_dump_json(
            indent=indent
        )

    @classmethod
    def deserialize(cls, data: str) -> GetMarketsGroupsMarketGroupIdDetail:
        """Deserializes a JSON string to a GetMarketsGroupsMarketGroupIdDetail model."""
        result = GetMarketsGroupsMarketGroupIdDetailRoot.model_validate_json(data).root
        return result


GetMarketsGroupsMarketGroupIdDetailRoot = RootModel[GetMarketsGroupsMarketGroupIdDetail]


@dataclass(slots=True, kw_only=True)
class GetMarketsGroupsMarketGroupId(EsiResponseBase):
    """Response model for market group details."""

    market_group: GetMarketsGroupsMarketGroupIdDetail

    def serialize(self, indent: int | None = 2) -> str:
        """Serializes the GetMarketsGroupsMarketGroupId to a JSON string."""
        return GetMarketsGroupsMarketGroupIdRoot(root=self).model_dump_json(
            indent=indent,
        )

    @classmethod
    def deserialize(cls, data: str) -> GetMarketsGroupsMarketGroupId:
        """Deserializes a JSON string to a GetMarketsGroupsMarketGroupId model."""
        result = GetMarketsGroupsMarketGroupIdRoot.model_validate_json(data).root
        return result


@dataclass(slots=True, kw_only=True)
class GetMarketsPricesDetail:
    """Detail for market prices response."""

    type_id: int
    average_price: float | None = None
    adjusted_price: float | None = None


@dataclass(slots=True, kw_only=True)
class GetMarketsPrices(EsiResponseBase):
    """Response model for market prices."""

    prices: list[GetMarketsPricesDetail]

    def serialize(self, indent: int | None = 2) -> str:
        """Serializes the GetMarketsPrices to a JSON string."""
        return GetMarketsPricesRoot(root=self).model_dump_json(
            indent=indent,
        )

    @classmethod
    def deserialize(cls, data: str) -> GetMarketsPrices:
        """Deserializes a JSON string to a GetMarketsPrices model."""
        result = GetMarketsPricesRoot.model_validate_json(data).root
        return result


@dataclass(slots=True, kw_only=True)
class GetMarketsRegionIdHistoryDetail:
    """Detail for market history response."""

    average: float
    date: str
    highest: float
    lowest: float
    order_count: int
    volume: int


GetMarketsRegionIdHistoryDetailRoot = RootModel[GetMarketsRegionIdHistoryDetail]


@dataclass(slots=True, kw_only=True)
class GetMarketsRegionIdHistory(EsiResponseBase):
    """Response model for market history."""

    region_id: int
    type_id: int
    history: list[GetMarketsRegionIdHistoryDetail]

    def serialize(self, indent: int | None = 2) -> str:
        """Serializes the GetMarketsRegionIdHistory to a JSON string."""
        return GetMarketsRegionIdHistoryRoot(root=self).model_dump_json(
            indent=indent,
        )

    @classmethod
    def deserialize(cls, data: str) -> GetMarketsRegionIdHistory:
        """Deserializes a JSON string to a GetMarketsRegionIdHistory model."""
        result = GetMarketsRegionIdHistoryRoot.model_validate_json(data).root
        return result


class CostIndicesActivity(StrEnum):
    COPYING = "copying"
    DUPLICATING = "duplicating"
    INVENTION = "invention"
    MANUFACTURING = "manufacturing"
    NONE = "none"
    REACTION = "reaction"
    RESEARCHING_MATERIAL_EFFICIENCY = "researching_material_efficiency"
    RESEARCHING_TECHNOLOGY = "researching_technology"
    RESEARCHING_TIME_EFFICIENCY = "researching_time_efficiency"
    REVERSE_ENGINEERING = "reverse_engineering"


@dataclass(slots=True, kw_only=True)
class CostIndicesDetail:
    """Detail for cost index response."""

    activity: CostIndicesActivity
    cost_index: float


@dataclass(slots=True, kw_only=True)
class GetIndustrySystemsDetail:
    """Detail for industry systems cost indices response."""

    solar_system_id: int
    cost_indices: list[CostIndicesDetail]


@dataclass(slots=True, kw_only=True)
class GetIndustrySystems(EsiResponseBase):
    """Response model for industry systems cost indices."""

    systems: list[GetIndustrySystemsDetail]

    def serialize(self, indent: int | None = 2) -> str:
        """Serializes the GetIndustrySystems to a JSON string."""
        return GetIndustrySystemsRoot(root=self).model_dump_json(
            indent=indent,
        )

    @classmethod
    def deserialize(cls, data: str) -> GetIndustrySystems:
        """Deserializes a JSON string to a GetIndustrySystems model."""
        result = GetIndustrySystemsRoot.model_validate_json(data).root
        return result


GetIndustrySystemsRoot = RootModel[GetIndustrySystems]
GetMarketsRegionIdHistoryRoot = RootModel[GetMarketsRegionIdHistory]
GetMarketsPricesRoot = RootModel[GetMarketsPrices]
GetMarketsRegionIdOrdersRoot = RootModel[GetMarketsRegionIdOrders]
GetMarketsGroupsRoot = RootModel[GetMarketsGroups]
GetMarketsGroupsMarketGroupIdRoot = RootModel[GetMarketsGroupsMarketGroupId]
