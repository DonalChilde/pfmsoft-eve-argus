"""Models related to the argus static data db.

In the record dataclass definition, the record key should come first, then the fields
in alphabetical order.
"""

from dataclasses import dataclass

from pydantic import RootModel


@dataclass(slots=True, kw_only=True)
class IndustryActivityRecord:
    activity_id: int
    description: str
    name: str


IndustryActivityDataset = dict[int, IndustryActivityRecord]
IndustryActivityDatasetRoot = RootModel[IndustryActivityDataset]


@dataclass(slots=True, kw_only=True)
class MarketGroupsRecord:
    market_group_id: int
    description: str
    has_types: bool
    icon_id: int | None
    int_path: tuple[int, ...]
    name: str
    parent_group_id: int | None
    str_path: tuple[str, ...]
    types: tuple[int, ...]


MarketGroupsDataset = dict[int, MarketGroupsRecord]
MarketGroupsDatasetRoot = RootModel[MarketGroupsDataset]


@dataclass(slots=True, kw_only=True)
class MapRegionsRecord:
    region_id: int
    constellation_ids: tuple[int, ...]
    description: str
    faction_id: int | None
    name: str
    nebula_id: int | None
    position_x: float
    position_y: float
    position_z: float
    wormhole_class_id: int | None


MapRegionsDataset = dict[int, MapRegionsRecord]
MapRegionsDatasetRoot = RootModel[MapRegionsDataset]


@dataclass(slots=True, kw_only=True)
class MapConstellationsRecord:
    constellation_id: int
    faction_id: int | None
    name: str
    position_x: float
    position_y: float
    position_z: float
    region_id: int
    solar_system_ids: tuple[int, ...]
    wormhole_class_id: int | None


MapConstellationsDataset = dict[int, MapConstellationsRecord]
MapConstellationsDatasetRoot = RootModel[MapConstellationsDataset]


@dataclass(slots=True, kw_only=True)
class MapSolarSystemsRecord:
    """Represents a solar system in the EVE Online universe."""

    solar_system_id: int
    border: bool
    constellation_id: int
    corridor: bool
    disallowed_anchor_categories: tuple[int, ...]
    disallowed_anchor_groups: tuple[int, ...]
    faction_id: int | None
    fringe: bool
    hub: bool
    international: bool
    luminosity: float
    name: str
    planet_ids: tuple[int, ...]
    position_x: float
    position_y: float
    position_z: float
    position2d_x: float | None
    position2d_y: float | None
    radius: float
    region_id: int
    regional: bool
    security_class: str | None
    security_status: float
    star_id: int | None
    stargate_ids: tuple[int, ...]
    visual_effect: str | None
    wormhole_class_id: int | None


MapSolarSystemsDataset = dict[int, MapSolarSystemsRecord]
MapSolarSystemsDatasetRoot = RootModel[MapSolarSystemsDataset]


@dataclass(slots=True, kw_only=True)
class GroupsRecord:
    """Represents a group in the EVE Online universe.

    -- Groups
    CREATE TABLE IF NOT EXISTS groups (
        group_id INTEGER PRIMARY KEY,
        anchorable INTEGER NOT NULL, --boolean represented as integer (0 or 1)
        anchored INTEGER NOT NULL, --boolean represented as integer (0 or 1)
        category_id INTEGER NOT NULL,
        fittable_non_singleton INTEGER NOT NULL, --boolean represented as integer (0 or 1)
        icon_id INTEGER,
        name TEXT,
        published INTEGER, --boolean represented as integer (0 or 1)
        use_base_price INTEGER NOT NULL, --boolean represented as integer (0 or 1)
        FOREIGN KEY (category_id) REFERENCES categories(category_id)
    ) STRICT;
    """

    group_id: int
    anchorable: bool
    anchored: bool
    category_id: int
    fittable_non_singleton: bool
    icon_id: int | None
    name: str | None
    published: bool | None
    use_base_price: bool


GroupsDataset = dict[int, GroupsRecord]
GroupsDatasetRoot = RootModel[GroupsDataset]


@dataclass(slots=True, kw_only=True)
class CategoriesRecord:
    """Represents a category in the EVE Online universe."""

    category_id: int
    icon_id: int | None
    name: str | None
    published: bool | None


CategoriesDataset = dict[int, CategoriesRecord]
CategoriesDatasetRoot = RootModel[CategoriesDataset]


@dataclass(slots=True, kw_only=True)
class RandomizedMaterials:
    material_type_id: int
    quantity_min: int
    quantity_max: int


@dataclass(slots=True, kw_only=True)
class TypeMaterialsRandomizedRecord:
    """Represents a randomized material component for a type in the EVE Online universe."""

    type_id: int
    materials: tuple[RandomizedMaterials, ...]


TypeMaterialsRandomizedDataset = dict[tuple[int, int], TypeMaterialsRandomizedRecord]
TypeMaterialsRandomizedDatasetRoot = RootModel[TypeMaterialsRandomizedDataset]


@dataclass(slots=True, kw_only=True)
class Materials:
    material_type_id: int
    quantity: int


@dataclass(slots=True, kw_only=True)
class TypeMaterialsRecord:
    """Represents the materials for a type in the EVE Online universe."""

    type_id: int
    materials: tuple[Materials, ...]


TypeMaterialsDataset = dict[int, TypeMaterialsRecord]
TypeMaterialsDatasetRoot = RootModel[TypeMaterialsDataset]


@dataclass(slots=True, kw_only=True)
class Color:
    """Represents a color in the EVE Online universe."""

    red: float
    green: float
    blue: float


@dataclass(slots=True, kw_only=True)
class MetaGroupsRecord:
    """Represents a meta group in the EVE Online universe.

    -- meta_groups
    CREATE TABLE IF NOT EXISTS meta_groups (
        meta_group_id INTEGER PRIMARY KEY,
        color TEXT, -- a json string representing the color as a dict.
        description TEXT,
        icon_id INTEGER,
        icon_suffix TEXT,
        name TEXT NOT NULL
    ) STRICT;
    """

    meta_group_id: int
    color: Color | None
    description: str | None
    icon_id: int | None
    icon_suffix: str | None
    name: str


MetaGroupsDataset = dict[int, MetaGroupsRecord]
MetaGroupsDatasetRoot = RootModel[MetaGroupsDataset]


@dataclass(slots=True, kw_only=True)
class TypesRecord:
    """Represents a type in the EVE Online universe.

    -- ref esd_datasets.py TypesRecord
    CREATE TABLE IF NOT EXISTS types (
        type_id INTEGER PRIMARY KEY,
        base_price REAL,
        capacity REAL,
        description TEXT,
        faction_id INTEGER,
        graphic_id INTEGER,
        group_id INTEGER NOT NULL,
        icon_id INTEGER,
        market_group_id INTEGER,
        mass REAL,
        meta_group_id INTEGER,
        meta_level INTEGER,
        name TEXT NOT NULL,
        packaged_volume REAL,
        portion_size INTEGER NOT NULL,
        published INTEGER NOT NULL, --boolean represented as integer (0 or 1)
        race_id INTEGER,
        radius REAL,
        ship_tree_group_id INTEGER,
        sound_id INTEGER,
        tech_level INTEGER,
        variation_parent_type_id INTEGER,
        volume REAL
    ) STRICT;
    """

    type_id: int
    base_price: float | None
    capacity: float | None
    description: str | None
    faction_id: int | None
    graphic_id: int | None
    group_id: int
    icon_id: int | None
    market_group_id: int | None
    mass: float | None
    meta_group_id: int | None
    meta_level: int | None
    name: str
    packaged_volume: float | None
    portion_size: int
    published: bool
    race_id: int | None
    radius: float | None
    ship_tree_group_id: int | None
    sound_id: int | None
    tech_level: int | None
    variation_parent_type_id: int | None
    volume: float | None


TypesDataset = dict[int, TypesRecord]
TypesDatasetRoot = RootModel[TypesDataset]
