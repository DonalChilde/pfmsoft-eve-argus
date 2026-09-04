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


class GetCorporationsCorporationIdIndustryJobsDetail_Status(StrEnum):
    """Enumeration for the status of corporation industry jobs."""

    ACTIVE = "active"
    CANCELLED = "cancelled"
    DELIVERED = "delivered"
    PAUSED = "paused"
    READY = "ready"
    REVERTED = "reverted"


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
    status: GetCorporationsCorporationIdIndustryJobsDetail_Status
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


class GetCorporationsCorporationIdBlueprintsDetail_LocationFlag(StrEnum):
    """Enumeration for the location flag of corporation blueprints."""

    ASSET_SAFETY = "AssetSafety"
    AUTOFIT = "AutoFit"
    BONUS = "Bonus"
    BOOSTER = "Booster"
    BOOSTER_BAY = "BoosterBay"
    CAPSULE = "Capsule"
    CAPSULEER_DELIVERIES = "CapsuleerDeliveries"
    CARGO = "Cargo"
    CORP_DELIVERIES = "CorpDeliveries"
    CORP_SAG_1 = "CorpSAG1"
    CORP_SAG_2 = "CorpSAG2"
    CORP_SAG_3 = "CorpSAG3"
    CORP_SAG_4 = "CorpSAG4"
    CORP_SAG_5 = "CorpSAG5"
    CORP_SAG_6 = "CorpSAG6"
    CORP_SAG_7 = "CorpSAG7"
    CORPORATION_GOAL_DELIVERIES = "CorporationGoalDeliveries"
    CRATE_LOOT = "CrateLoot"
    DELIVERIES = "Deliveries"
    DRONE_BAY = "DroneBay"
    DUST_BATTLE = "DustBattle"
    DUST_DATABANK = "DustDatabank"
    EXPEDITION_HOLD = "ExpeditionHold"
    FIGHTER_BAY = "FighterBay"
    FIGHTER_TUBE_0 = "FighterTube0"
    FIGHTER_TUBE_1 = "FighterTube1"
    FIGHTER_TUBE_2 = "FighterTube2"
    FIGHTER_TUBE_3 = "FighterTube3"
    FIGHTER_TUBE_4 = "FighterTube4"
    FLEET_HANGAR = "FleetHangar"
    FRIGATE_ESCAPE_BAY = "FrigateEscapeBay"
    HANGAR = "Hangar"
    HANGAR_ALL = "HangarAll"
    HI_SLOT_0 = "HiSlot0"
    HI_SLOT_1 = "HiSlot1"
    HI_SLOT_2 = "HiSlot2"
    HI_SLOT_3 = "HiSlot3"
    HI_SLOT_4 = "HiSlot4"
    HI_SLOT_5 = "HiSlot5"
    HI_SLOT_6 = "HiSlot6"
    HI_SLOT_7 = "HiSlot7"
    HIDDEN_MODIFIERS = "HiddenModifiers"
    IMPLANT = "Implant"
    IMPOUNDED = "Impounded"
    INFRASTRUCTURE_HANGAR = "InfrastructureHangar"
    JUNKYARD_REPROCESSED = "JunkyardReprocessed"
    JUNKYARD_TRASHED = "JunkyardTrashed"
    LO_SLOT_0 = "LoSlot0"
    LO_SLOT_1 = "LoSlot1"
    LO_SLOT_2 = "LoSlot2"
    LO_SLOT_3 = "LoSlot3"
    LO_SLOT_4 = "LoSlot4"
    LO_SLOT_5 = "LoSlot5"
    LO_SLOT_6 = "LoSlot6"
    LO_SLOT_7 = "LoSlot7"
    LOCKED = "Locked"
    MED_SLOT_0 = "MedSlot0"
    MED_SLOT_1 = "MedSlot1"
    MED_SLOT_2 = "MedSlot2"
    MED_SLOT_3 = "MedSlot3"
    MED_SLOT_4 = "MedSlot4"
    MED_SLOT_5 = "MedSlot5"
    MED_SLOT_6 = "MedSlot6"
    MED_SLOT_7 = "MedSlot7"
    MOBILE_DEPOT_HOLD = "MobileDepotHold"
    MOON_MATERIAL_BAY = "MoonMaterialBay"
    OFFICE_FOLDER = "OfficeFolder"
    PILOT = "Pilot"
    PLANET_SURFACE = "PlanetSurface"
    QUAFE_BAY = "QuafeBay"
    QUANTUM_CORE_ROOM = "QuantumCoreRoom"
    REWARD = "Reward"
    RIG_SLOT_0 = "RigSlot0"
    RIG_SLOT_1 = "RigSlot1"
    RIG_SLOT_2 = "RigSlot2"
    RIG_SLOT_3 = "RigSlot3"
    RIG_SLOT_4 = "RigSlot4"
    RIG_SLOT_5 = "RigSlot5"
    RIG_SLOT_6 = "RigSlot6"
    RIG_SLOT_7 = "RigSlot7"
    SECONDARY_STORAGE = "SecondaryStorage"
    SERVICE_SLOT_0 = "ServiceSlot0"
    SERVICE_SLOT_1 = "ServiceSlot1"
    SERVICE_SLOT_2 = "ServiceSlot2"
    SERVICE_SLOT_3 = "ServiceSlot3"
    SERVICE_SLOT_4 = "ServiceSlot4"
    SERVICE_SLOT_5 = "ServiceSlot5"
    SERVICE_SLOT_6 = "ServiceSlot6"
    SERVICE_SLOT_7 = "ServiceSlot7"
    SHIP_HANGAR = "ShipHangar"
    SHIP_OFFLINE = "ShipOffline"
    SKILL = "Skill"
    SKILL_IN_TRAINING = "SkillInTraining"
    SPECIALIZED_AMMO_HOLD = "SpecializedAmmoHold"
    SPECIALIZED_ASTEROID_HOLD = "SpecializedAsteroidHold"
    SPECIALIZED_COMMAND_CENTER_HOLD = "SpecializedCommandCenterHold"
    SPECIALIZED_FUEL_BAY = "SpecializedFuelBay"
    SPECIALIZED_GAS_HOLD = "SpecializedGasHold"
    SPECIALIZED_ICE_HOLD = "SpecializedIceHold"
    SPECIALIZED_INDUSTRIAL_SHIP_HOLD = "SpecializedIndustrialShipHold"
    SPECIALIZED_LARGE_SHIP_HOLD = "SpecializedLargeShipHold"
    SPECIALIZED_MATERIAL_BAY = "SpecializedMaterialBay"
    SPECIALIZED_MEDIUM_SHIP_HOLD = "SpecializedMediumShipHold"
    SPECIALIZED_MINERAL_HOLD = "SpecializedMineralHold"
    SPECIALIZED_ORE_HOLD = "SpecializedOreHold"
    SPECIALIZED_PLANETARY_COMMODITIES_HOLD = "SpecializedPlanetaryCommoditiesHold"
    SPECIALIZED_SALVAGE_HOLD = "SpecializedSalvageHold"
    SPECIALIZED_SHIP_HOLD = "SpecializedShipHold"
    SPECIALIZED_SMALL_SHIP_HOLD = "SpecializedSmallShipHold"
    STRUCTURE_ACTIVE = "StructureActive"
    STRUCTURE_FUEL = "StructureFuel"
    STRUCTURE_INACTIVE = "StructureInactive"
    STRUCTURE_OFFLINE = "StructureOffline"
    SUB_SYSTEM_BAY = "SubSystemBay"
    SUB_SYSTEM_SLOT_0 = "SubSystemSlot0"
    SUB_SYSTEM_SLOT_1 = "SubSystemSlot1"
    SUB_SYSTEM_SLOT_2 = "SubSystemSlot2"
    SUB_SYSTEM_SLOT_3 = "SubSystemSlot3"
    SUB_SYSTEM_SLOT_4 = "SubSystemSlot4"
    SUB_SYSTEM_SLOT_5 = "SubSystemSlot5"
    SUB_SYSTEM_SLOT_6 = "SubSystemSlot6"
    SUB_SYSTEM_SLOT_7 = "SubSystemSlot7"
    UNLOCKED = "Unlocked"
    WALLET = "Wallet"
    WARDROBE = "Wardrobe"


@dataclass(slots=True, kw_only=True)
class GetCorporationsCorporationIdBlueprintsDetail:
    """Detail for corporation blueprints response.

    Note that ``quantity`` is -1 for a blueprint original, -2 for a blueprint copy,
    and a positive integer for an unprocessed stack of originals (e.g. fresh from the
    market). ``runs`` is -1 for an original, otherwise the number of runs remaining
    on the copy.
    """

    item_id: int
    type_id: int
    location_id: int
    location_flag: GetCorporationsCorporationIdBlueprintsDetail_LocationFlag
    quantity: int
    time_efficiency: int
    material_efficiency: int
    runs: int


@dataclass(slots=True, kw_only=True)
class GetCorporationsCorporationIdBlueprints(EsiResponseBase):
    """Response model for corporation blueprints."""

    corporation_id: int
    """The corporation ID for which the blueprints were fetched."""
    blueprints: list[GetCorporationsCorporationIdBlueprintsDetail]


class GetCorporationsCorporationIdBlueprintsResponse(EsiResponseBaseModel):
    """Pydantic BaseModel for GetCorporationsCorporationIdBlueprints response."""

    response_data: GetCorporationsCorporationIdBlueprints


@dataclass(slots=True, kw_only=True)
class GetUniverseTypes(EsiResponseBase):
    """Response model for universe types."""

    type_ids: list[int]


class GetUniverseTypesResponse(EsiResponseBaseModel):
    """Pydantic BaseModel for GetUniverseTypes response."""

    response_data: GetUniverseTypes
