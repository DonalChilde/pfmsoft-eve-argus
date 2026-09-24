"""Data models for EVE Online Static Data Export (ESD) datasets."""

from dataclasses import dataclass, field
from typing import Any, Self

from pydantic import BaseModel

from pfmsoft.eve_argus.models.types import LanguageEnum


class SdeDataset(BaseModel):
    dataset: Any

    def serialize(self, indent: int | None = None) -> str:
        """Serialize the dataset to a JSON string."""
        return self.model_dump_json(indent=indent)

    @classmethod
    def deserialize(cls, data: str) -> Self:
        """Deserialize the dataset from a JSON string."""
        return cls.model_validate_json(data)


@dataclass(slots=True, kw_only=True)
class Blueprint_Material:
    typeID: int
    quantity: int


@dataclass(slots=True, kw_only=True)
class Blueprint_Skill:
    typeID: int
    level: int


@dataclass(slots=True, kw_only=True)
class Blueprint_Products:
    typeID: int
    quantity: int
    probability: float | None = None


@dataclass(slots=True, kw_only=True)
class Blueprint_Activity:
    materials: list[Blueprint_Material] | None = field(
        default_factory=list[Blueprint_Material]
    )
    skills: list[Blueprint_Skill] | None = field(default_factory=list[Blueprint_Skill])
    products: list[Blueprint_Products] | None = field(
        default_factory=list[Blueprint_Products]
    )
    time: int

    def __post_init__(self) -> None:
        """Check for duplicate skill entries in the activity."""
        # If the list of skill requirements contains duplicates, only keep the one with
        # the highest level.
        if self.skills:
            unique_skills: dict[int, Blueprint_Skill] = {}
            for skill in self.skills:
                if (
                    skill.typeID not in unique_skills
                    or skill.level > unique_skills[skill.typeID].level
                ):
                    unique_skills[skill.typeID] = skill
            self.skills = list(unique_skills.values())


@dataclass(slots=True, kw_only=True)
class BlueprintActivities:
    copying: Blueprint_Activity | None = None
    invention: Blueprint_Activity | None = None
    manufacturing: Blueprint_Activity | None = None
    reaction: Blueprint_Activity | None = None
    research_material: Blueprint_Activity | None = None
    research_time: Blueprint_Activity | None = None


@dataclass(slots=True, kw_only=True)
class BlueprintRecord:
    """Record for a specific blueprint.

    - source: dev/tmp/sde-yaml/3464040
    - records: 5082 (key: int)
    - valid: 5082, skipped: 0

    | Field              | Required | Type       | Presence  |
    | ------------------ | -------- | ---------- | --------- |
    | activities         | yes      | Activities | 5082/5082 |
    | blueprintTypeID    | yes      | int        | 5082/5082 |
    | maxProductionLimit | yes      | int        | 5082/5082 |
    """

    blueprintTypeID: int
    activities: BlueprintActivities
    maxProductionLimit: int | None = None


class BlueprintsDataset(SdeDataset):
    dataset: dict[int, BlueprintRecord]


@dataclass(slots=True, kw_only=True)
class TypeMaterials_Material:
    materialTypeID: int
    quantity: int


@dataclass(slots=True, kw_only=True)
class TypeMaterials_RandomizedMaterial:
    materialTypeID: int
    quantityMax: int
    quantityMin: int


@dataclass(slots=True, kw_only=True)
class TypeMaterialsRecord:
    """Record for a specific type's materials.

    - source: dev/tmp/sde-yaml/3464040
    - records: 9551 (key: int)
    - valid: 9551, skipped: 0

    | Field               | Required | Type                          | Presence  |
    | ------------------- | -------- | ----------------------------- | --------- |
    | materials           | no       | list[MaterialsItem]           | 9541/9551 |
    | randomizedMaterials | no       | list[RandomizedMaterialsItem] | 10/9551   |
    """

    materials: list[TypeMaterials_Material] | None = field(
        default_factory=list[TypeMaterials_Material]
    )
    randomized_materials: list[TypeMaterials_RandomizedMaterial] | None = field(
        default_factory=list[TypeMaterials_RandomizedMaterial]
    )


class TypeMaterialsDataset(SdeDataset):
    dataset: dict[int, TypeMaterialsRecord]


@dataclass(slots=True, kw_only=True)
class LocalizedString:
    """Localized string for a specific language."""

    en: str
    de: str = "NOT_DEFINED"
    fr: str = "NOT_DEFINED"
    ja: str = "NOT_DEFINED"
    ru: str = "NOT_DEFINED"
    zh: str = "NOT_DEFINED"
    es: str = "NOT_DEFINED"
    ko: str = "NOT_DEFINED"


@dataclass(slots=True, kw_only=True)
class TypesRecord:
    """Record for a specific type.

    - source: dev/tmp/sde-yaml/3464040
    - records: 52863 (key: int)
    - valid: 52863, skipped: 0

    | Field                 | Required | Type        | Presence    |
    | --------------------- | -------- | ----------- | ----------- |
    | basePrice             | no       | float       | 13933/52863 |
    | capacity              | no       | float       | 10009/52863 |
    | description           | no       | Description | 34299/52863 |
    | factionID             | no       | int         | 1376/52863  |
    | graphicID             | no       | int         | 18720/52863 |
    | groupID               | yes      | int         | 52863/52863 |
    | iconID                | no       | int         | 22808/52863 |
    | marketGroupID         | no       | int         | 19667/52863 |
    | mass                  | no       | float       | 21228/52863 |
    | metaGroupID           | no       | int         | 13798/52863 |
    | metaLevel             | no       | int         | 8204/52863  |
    | name                  | yes      | Name        | 52863/52863 |
    | packagedVolume        | no       | float       | 46748/52863 |
    | portionSize           | yes      | int         | 52863/52863 |
    | published             | yes      | bool        | 52863/52863 |
    | raceID                | no       | int         | 23120/52863 |
    | radius                | no       | float       | 15599/52863 |
    | shipTreeGroupID       | no       | int         | 934/52863   |
    | soundID               | no       | int         | 5085/52863  |
    | techLevel             | no       | int         | 10075/52863 |
    | variationParentTypeID | no       | int         | 4796/52863  |
    | volume                | no       | float       | 46748/52863 |
    """

    basePrice: float | None = None
    capacity: float | None = None
    description: LocalizedString | None = None
    factionID: int | None = None
    graphicID: int | None = None
    groupID: int
    iconID: int | None = None
    marketGroupID: int | None = None
    mass: float | None = None
    metaGroupID: int | None = None
    metaLevel: int | None = None
    name: LocalizedString
    packagedVolume: float | None = None
    portionSize: int
    published: bool
    raceID: int | None = None
    radius: float | None = None
    shipTreeGroupID: int | None = None
    soundID: int | None = None
    techLevel: int | None = None
    variationParentTypeID: int | None = None
    volume: float | None = None

    def name_localized(self, language: LanguageEnum = LanguageEnum.EN) -> str:
        """Get the localized name for the specified language.

        Args:
            language (LanguageEnum): The language code (default: LanguageEnum.EN).

        Returns:
            str: The localized name.
        """
        return getattr(self.name, language, self.name.en)

    def description_localized(self, language: LanguageEnum = LanguageEnum.EN) -> str:
        """Get the localized description for the specified language.

        Args:
            language (LanguageEnum): The language code (default: LanguageEnum.EN).

        Returns:
            str: The localized description.
        """
        if self.description is None:
            return "NOT_DEFINED"
        return getattr(self.description, language, self.description.en)


class TypesDataset(SdeDataset):
    dataset: dict[int, TypesRecord]


@dataclass(slots=True, kw_only=True)
class Color:
    b: float
    g: float
    r: float


@dataclass(slots=True, kw_only=True)
class MetaGroupsRecord:
    """Record for a specific meta group.

    - source: dev/tmp/sde-yaml/3464040
    - records: 13 (key: int)
    - valid: 13, skipped: 0

    | Field       | Required | Type        | Presence |
    | ----------- | -------- | ----------- | -------- |
    | color       | no       | Color       | 10/13    |
    | description | no       | Description | 3/13     |
    | iconID      | no       | int         | 12/13    |
    | iconSuffix  | no       | str         | 12/13    |
    | name        | yes      | Name        | 13/13    |
    """

    name: LocalizedString
    description: LocalizedString | None = None
    iconID: int | None = None
    iconSuffix: str | None = None
    color: Color | None = None

    def name_localized(self, language: LanguageEnum = LanguageEnum.EN) -> str:
        """Get the localized name for the specified language.

        Args:
            language (LanguageEnum): The language code (default: LanguageEnum.EN).

        Returns:
            str: The localized name.
        """
        return getattr(self.name, language, self.name.en)

    def description_localized(self, language: LanguageEnum = LanguageEnum.EN) -> str:
        """Get the localized description for the specified language.

        Args:
            language (LanguageEnum): The language code (default: LanguageEnum.EN).

        Returns:
            str: The localized description.
        """
        if self.description is None:
            return "NOT_DEFINED"
        return getattr(self.description, language, self.description.en)


class MetaGroupsDataset(SdeDataset):
    dataset: dict[int, MetaGroupsRecord]


@dataclass(slots=True, kw_only=True)
class CategoriesRecord:
    """Record for a specific category.

    - source: dev/tmp/sde-yaml/3464040
    - records: 48 (key: int)
    - valid: 48, skipped: 0

    | Field     | Required | Type | Presence |
    | --------- | -------- | ---- | -------- |
    | iconID    | no       | int  | 13/48    |
    | name      | yes      | Name | 48/48    |
    | published | yes      | bool | 48/48    |
    """

    name: LocalizedString
    published: bool
    iconID: int | None = None

    def name_localized(self, language: LanguageEnum = LanguageEnum.EN) -> str:
        """Get the localized name for the specified language.

        Args:
            language (LanguageEnum): The language code (default: LanguageEnum.EN).

        Returns:
            str: The localized name.
        """
        return getattr(self.name, language, self.name.en)


class CategoriesDataset(SdeDataset):
    dataset: dict[int, CategoriesRecord]


@dataclass(slots=True, kw_only=True)
class GroupsRecord:
    """Record for a specific group.

    - source: dev/tmp/sde-yaml/3464040
    - records: 1610 (key: int)
    - valid: 1610, skipped: 0

    | Field                | Required | Type | Presence  |
    | -------------------- | -------- | ---- | --------- |
    | anchorable           | yes      | bool | 1610/1610 |
    | anchored             | yes      | bool | 1610/1610 |
    | categoryID           | yes      | int  | 1610/1610 |
    | fittableNonSingleton | yes      | bool | 1610/1610 |
    | iconID               | no       | int  | 769/1610  |
    | name                 | yes      | Name | 1610/1610 |
    | published            | yes      | bool | 1610/1610 |
    | useBasePrice         | yes      | bool | 1610/1610 |

    """

    anchorable: bool
    anchored: bool
    categoryID: int
    fittableNonSingleton: bool
    iconID: int | None = None
    name: LocalizedString
    published: bool
    useBasePrice: bool

    def name_localized(self, language: LanguageEnum = LanguageEnum.EN) -> str:
        """Get the localized name for the specified language.

        Args:
            language (LanguageEnum): The language code (default: LanguageEnum.EN).

        Returns:
            str: The localized name.
        """
        return getattr(self.name, language, self.name.en)


class GroupsDataset(SdeDataset):
    dataset: dict[int, GroupsRecord]


@dataclass(slots=True, kw_only=True)
class IndustryActivitiesRecord:
    """Record for a specific industrial activity.

    - source: dev/tmp/sde-yaml/3464040
    - records: 6 (key: int)
    - valid: 6, skipped: 0

    | Field       | Required | Type | Presence |
    | ----------- | -------- | ---- | -------- |
    | description | yes      | str  | 6/6      |
    | name        | yes      | str  | 6/6      |
    """

    description: LocalizedString
    name: LocalizedString

    def name_localized(self, language: LanguageEnum = LanguageEnum.EN) -> str:
        """Get the localized name for the specified language.

        Args:
            language (LanguageEnum): The language code (default: LanguageEnum.EN).

        Returns:
            str: The localized name.
        """
        return getattr(self.name, language, self.name.en)

    def description_localized(self, language: LanguageEnum = LanguageEnum.EN) -> str:
        """Get the localized description for the specified language.

        Args:
            language (LanguageEnum): The language code (default: LanguageEnum.EN).

        Returns:
            str: The localized description.
        """
        return getattr(self.description, language, self.description.en)


class IndustryActivitiesDataset(SdeDataset):
    dataset: dict[int, IndustryActivitiesRecord]


@dataclass(slots=True, kw_only=True)
class Position:
    """A 3d position."""

    x: float
    y: float
    z: float


@dataclass(slots=True, kw_only=True)
class MapRegionsRecord:
    """Record for a specific map region.

    - source: dev/tmp/sde-yaml/3464040
    - records: 114 (key: int)
    - valid: 114, skipped: 0

    | Field            | Required | Type        | Presence |
    | ---------------- | -------- | ----------- | -------- |
    | constellationIDs | yes      | list[int]   | 114/114  |
    | description      | no       | Description | 70/114   |
    | factionID        | no       | int         | 33/114   |
    | name             | yes      | Name        | 114/114  |
    | nebulaID         | yes      | int         | 114/114  |
    | position         | yes      | Position    | 114/114  |
    | wormholeClassID  | no       | int         | 108/114  |
    """

    constellationIDs: list[int]
    description: LocalizedString | None = None
    factionID: int | None = None
    name: LocalizedString
    nebulaID: int
    position: Position
    wormholeClassID: int | None = None

    def name_localized(self, language: LanguageEnum = LanguageEnum.EN) -> str:
        """Get the localized name for the specified language.

        Args:
            language (LanguageEnum): The language code (default: LanguageEnum.EN).

        Returns:
            str: The localized name.
        """
        return getattr(self.name, language, self.name.en)

    def description_localized(self, language: LanguageEnum = LanguageEnum.EN) -> str:
        """Get the localized description for the specified language.

        Args:
            language (LanguageEnum): The language code (default: LanguageEnum.EN).

        Returns:
            str: The localized description.
        """
        if self.description is None:
            return "NOT_DEFINED"
        return getattr(self.description, language, self.description.en)


class MapRegionsDataset(SdeDataset):
    dataset: dict[int, MapRegionsRecord]


@dataclass(slots=True, kw_only=True)
class MapConstellationsRecord:
    """Record for a specific map constellation.

    - source: dev/tmp/sde-yaml/3464040
    - records: 1184 (key: int)
    - valid: 1184, skipped: 0

    | Field           | Required | Type      | Presence  |
    | --------------- | -------- | --------- | --------- |
    | factionID       | no       | int       | 386/1184  |
    | name            | yes      | Name      | 1184/1184 |
    | position        | yes      | Position  | 1184/1184 |
    | regionID        | yes      | int       | 1184/1184 |
    | solarSystemIDs  | yes      | list[int] | 1184/1184 |
    | wormholeClassID | no       | int       | 1127/1184 |
    """

    factionID: int | None = None
    name: LocalizedString
    position: Position
    regionID: int
    solarSystemIDs: list[int]
    wormholeClassID: int | None = None

    def name_localized(self, language: LanguageEnum = LanguageEnum.EN) -> str:
        """Get the localized name for the specified language.

        Args:
            language (LanguageEnum): The language code (default: LanguageEnum.EN).

        Returns:
            str: The localized name.
        """
        return getattr(self.name, language, self.name.en)


class MapConstellationsDataset(SdeDataset):
    dataset: dict[int, MapConstellationsRecord]


@dataclass(slots=True, kw_only=True)
class Position2D:
    x: float
    y: float


@dataclass(slots=True, kw_only=True)
class MapSolarSystemsRecord:
    """Record for a specific map solar system.

    - source: dev/tmp/sde-yaml/3464040
    - records: 8490 (key: int)
    - valid: 8490, skipped: 0

    | Field                      | Required | Type       | Presence  |
    | -------------------------- | -------- | ---------- | --------- |
    | border                     | no       | bool       | 2012/8490 |
    | constellationID            | yes      | int        | 8490/8490 |
    | corridor                   | no       | bool       | 1931/8490 |
    | disallowedAnchorCategories | no       | list[int]  | 591/8490  |
    | disallowedAnchorGroups     | no       | list[int]  | 79/8490   |
    | factionID                  | no       | int        | 70/8490   |
    | fringe                     | no       | bool       | 787/8490  |
    | hub                        | no       | bool       | 2715/8490 |
    | international              | no       | bool       | 109/8490  |
    | luminosity                 | no       | float      | 5484/8490 |
    | name                       | yes      | Name       | 8490/8490 |
    | planetIDs                  | no       | list[int]  | 8088/8490 |
    | position                   | yes      | Position   | 8490/8490 |
    | position2D                 | no       | Position2D | 5485/8490 |
    | radius                     | yes      | float      | 8490/8490 |
    | regionID                   | yes      | int        | 8490/8490 |
    | regional                   | no       | bool       | 542/8490  |
    | securityClass              | no       | str        | 5193/8490 |
    | securityStatus             | yes      | float      | 8490/8490 |
    | starID                     | no       | int        | 8089/8490 |
    | stargateIDs                | no       | list[int]  | 5268/8490 |
    | visualEffect               | no       | str        | 130/8490  |
    | wormholeClassID            | no       | int        | 692/8490  |
    """

    border: bool | None = None
    constellationID: int
    corridor: bool | None = None
    disallowedAnchorCategories: list[int] | None = None
    disallowedAnchorGroups: list[int] | None = None
    factionID: int | None = None
    fringe: bool | None = None
    hub: bool | None = None
    international: bool | None = None
    luminosity: float | None = None
    name: LocalizedString
    planetIDs: list[int] | None = None
    position: Position
    position2D: Position2D | None = None
    radius: float
    regionID: int
    regional: bool | None = None
    securityClass: str | None = None
    securityStatus: float
    starID: int | None = None
    stargateIDs: list[int] | None = None
    visualEffect: str | None = None
    wormholeClassID: int | None = None


class MapSolarSystemsDataset(SdeDataset):
    dataset: dict[int, MapSolarSystemsRecord]
