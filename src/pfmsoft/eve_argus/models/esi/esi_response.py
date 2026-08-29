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
from typing import Any, Self

from pydantic import BaseModel
from whenever import Instant


class EsiResponseBaseModel(BaseModel):
    """BaseModel class for ESI response models.

    This class is a wrapper for serialization and validation of ESI response data.
    """

    response_data: Any

    def serialize(self, indent: int | None = 2) -> str:
        """Serializes the ESI response model to a JSON string."""
        return self.model_dump_json(indent=indent)

    @classmethod
    def deserialize(cls, data: str) -> Self:
        """Deserializes a JSON string to an ESI response model."""
        return cls.model_validate_json(data)


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


class GetMarketsRegionIdOrdersResponse(EsiResponseBaseModel):
    """Pydantic BaseModel for GetMarketsRegionIdOrders response."""

    response_data: GetMarketsRegionIdOrders


@dataclass(slots=True, kw_only=True)
class GetMarketsGroups(EsiResponseBase):
    """Response model for market groups."""

    market_group_ids: list[int]


class GetMarketsGroupsResponse(EsiResponseBaseModel):
    """Pydantic BaseModel for GetMarketsGroups response."""

    response_data: GetMarketsGroups


@dataclass(slots=True, kw_only=True)
class GetMarketsGroupsMarketGroupIdDetail:
    """Response model for market group details."""

    market_group_id: int
    """The market group ID for which the details were fetched."""
    name: str
    description: str
    parent_group_id: int | None = None
    types: list[int] = field(default_factory=list[int])


@dataclass(slots=True, kw_only=True)
class GetMarketsGroupsMarketGroupId(EsiResponseBase):
    """Response model for market group details."""

    market_group: GetMarketsGroupsMarketGroupIdDetail


class GetMarketsGroupsMarketGroupIdCollectedResponse(EsiResponseBaseModel):
    """Pydantic BaseModel for GetMarketsGroupsMarketGroupId response."""

    response_data: dict[int, GetMarketsGroupsMarketGroupId]


@dataclass(slots=True, kw_only=True)
class GetMarketsPricesDetail:
    """Detail for market prices response."""

    type_id: int
    average_price: float | None = None
    adjusted_price: float | None = None


@dataclass(slots=True, kw_only=True)
class GetMarketsPrices(EsiResponseBase):
    """Response model for market prices."""

    markets_prices: list[GetMarketsPricesDetail]


class GetMarketsPricesResponse(EsiResponseBaseModel):
    """Pydantic BaseModel for GetMarketsPrices response."""

    response_data: GetMarketsPrices


@dataclass(slots=True, kw_only=True)
class GetMarketsRegionIdHistoryDetail:
    """Detail for market history response."""

    average: float
    date: str
    highest: float
    lowest: float
    order_count: int
    volume: int


@dataclass(slots=True, kw_only=True)
class GetMarketsRegionIdHistory(EsiResponseBase):
    """Response model for market history."""

    region_id: int
    type_id: int
    history: list[GetMarketsRegionIdHistoryDetail]


class GetMarketsRegionIdHistoryCollectedResponse(EsiResponseBaseModel):
    """Pydantic BaseModel for GetMarketsRegionIdHistory response."""

    response_data: list[GetMarketsRegionIdHistory]
    """The response data is a dictionary with keys as tuples of (region_id, type_id) 
        and values as GetMarketsRegionIdHistory instances."""


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

    industry_systems: list[GetIndustrySystemsDetail]


class GetIndustrySystemsResponse(EsiResponseBaseModel):
    """Pydantic BaseModel for GetIndustrySystems response."""

    response_data: GetIndustrySystems


class PostUniverseNamesCategory(StrEnum):
    """Enumeration for universe names categories."""

    ALLIANCE = "alliance"
    CHARACTER = "character"
    CONSTELLATION = "constellation"
    CORPORATION = "corporation"
    FACTION = "faction"
    INVENTORY_TYPE = "inventory_type"
    REGION = "region"
    SOLAR_SYSTEM = "solar_system"
    STATION = "station"


@dataclass(slots=True, kw_only=True)
class PostUniverseNamesDetail:
    """Detail for universe names response."""

    category: PostUniverseNamesCategory
    id: int
    name: str


@dataclass(slots=True, kw_only=True)
class PostUniverseNames(EsiResponseBase):
    """Response model for universe names."""

    names: list[PostUniverseNamesDetail]


class PostUniverseNamesResponse(EsiResponseBaseModel):
    """Pydantic BaseModel for PostUniverseNames response."""

    response_data: PostUniverseNames


@dataclass(slots=True, kw_only=True)
class GetCorporationsCorporationIdIndustryJobsDetail:
    """Detail for corporation industry jobs response."""

    activity_id: int
    blueprint_id: int
    blueprint_location_id: int
    blueprint_type_id: int
    completed_character_id: int | None = None
    completed_date: str | None = None
    cost: float | None = None
    duration: int
    end_date: str
    facility_id: int
    installer_id: int
    job_id: int
    licensed_runs: int | None = None
    location_id: int
    output_location_id: int
    pause_date: str | None = None
    probability: float | None = None
    product_type_id: int | None = None
    runs: int
    start_date: str
    status: str
    successful_runs: int | None = None


@dataclass(slots=True, kw_only=True)
class GetCorporationsCorporationIdIndustryJobs(EsiResponseBase):
    """Response model for corporation industry jobs."""

    corporation_id: int
    """The corporation ID for which the industry jobs were fetched."""
    industry_jobs: list[GetCorporationsCorporationIdIndustryJobsDetail]


class GetCorporationsCorporationIdIndustryJobsResponse(EsiResponseBaseModel):
    """Pydantic BaseModel for GetCorporationsCorporationIdIndustryJobs response."""

    response_data: GetCorporationsCorporationIdIndustryJobs


@dataclass(slots=True, kw_only=True)
class GetUniverseTypes(EsiResponseBase):
    """Response model for universe types."""

    type_ids: list[int]


class GetUniverseTypesResponse(EsiResponseBaseModel):
    """Pydantic BaseModel for GetUniverseTypes response."""

    response_data: GetUniverseTypes
