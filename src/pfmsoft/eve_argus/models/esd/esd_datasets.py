"""Data models for EVE Online Static Data Export (ESD) datasets."""

from dataclasses import dataclass, field

from pydantic import RootModel


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

    blueprint_type_id: int
    activities: BlueprintActivities
    max_production_limit: int | None = None


BlueprintsDataset = dict[int, BlueprintRecord]
BlueprintDatasetRoot = RootModel[BlueprintsDataset]


@dataclass(slots=True, kw_only=True)
class TypeMaterials_Material:
    material_type_id: int
    quantity: int


@dataclass(slots=True, kw_only=True)
class TypeMaterials_RandomizedMaterial:
    material_type_id: int
    quantity_max: int
    quantity_min: int


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


TypeMaterialsDataset = dict[int, TypeMaterialsRecord]
TypeMaterialsDatasetRoot = RootModel[TypeMaterialsDataset]


@dataclass(slots=True, kw_only=True)
class LocalizedString:
    """Localized string for a specific language."""

    en: str
    de: str | None = None
    fr: str | None = None
    ja: str | None = None
    ru: str | None = None
    zh: str | None = None
    es: str | None = None
    ko: str | None = None


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


TypesDataset = dict[int, TypesRecord]
TypesDatasetRoot = RootModel[TypesDataset]


@dataclass(slots=True, kw_only=True)
class Color:
    b: int
    g: int
    r: int


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


MetaGroupsDataset = dict[int, MetaGroupsRecord]
MetaGroupsDatasetRoot = RootModel[MetaGroupsDataset]


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


CategoriesDataset = dict[int, CategoriesRecord]
CategoriesDatasetRoot = RootModel[CategoriesDataset]


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


GroupsDataset = dict[int, GroupsRecord]
GroupsDatasetRoot = RootModel[GroupsDataset]
