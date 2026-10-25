"""Test static read/write entry points and representative SQLite round trips."""

from collections.abc import Callable
from sqlite3 import Connection
from typing import Any

import pytest
from pfmsoft.eve_sd.helpers.sde_metadata import (
    SdeMetadata,
    SdeVariant,
    SourceMedia,
)

from pfmsoft.eve_argus.esd import models as ESD
from pfmsoft.eve_argus.models.types import LanguageEnum
from pfmsoft.eve_argus.static import models as ASM
from pfmsoft.eve_argus.static import read, util, write


def test_blueprints_round_trip(static_connection: Connection) -> None:
    """The public writer and reader preserve nested blueprint records."""
    write.types(
        static_connection,
        dataset=ESD.TypesDataset(
            dataset={
                type_id: ESD.TypesRecord(
                    groupID=1,
                    name=ESD.LocalizedString(en=f"Type {type_id}"),
                    portionSize=1,
                    published=True,
                )
                for type_id in (100, 101, 102, 103)
            }
        ),
    )
    write.blueprints(
        static_connection,
        dataset=ESD.BlueprintsDataset.model_validate(
            {
                "dataset": {
                    100: {
                        "blueprintTypeID": 100,
                        "maxProductionLimit": 10,
                        "activities": {
                            "manufacturing": {
                                "time": 60,
                                "materials": [{"typeID": 102, "quantity": 5}],
                                "skills": [{"typeID": 103, "level": 3}],
                                "products": [{"typeID": 101, "quantity": 1}],
                            }
                        },
                    }
                }
            }
        ),
    )

    assert read.blueprints(static_connection) == {
        100: ASM.BlueprintRecord(
            blueprint_type_id=100,
            max_production_limit=10,
            activities=ASM.BlueprintActivities(
                manufacturing=ASM.Blueprint_Activity(
                    time=60,
                    materials=(ASM.Blueprint_Material(type_id=102, quantity=5),),
                    skills=(ASM.Blueprint_Skill(type_id=103, level=3),),
                    products=(ASM.Blueprint_Product(type_id=101, quantity=1),),
                )
            ),
        )
    }


@pytest.mark.parametrize("value", [True, False, None])
def test_nullable_type_flags_round_trip(
    static_connection: Connection, value: bool | None
) -> None:
    """Preserve nullable type flags as bool/None rather than SQLite integers."""
    write.types(
        static_connection,
        dataset=ESD.TypesDataset.model_validate(
            {
                "dataset": {
                    1: {
                        "groupID": 1,
                        "name": {"en": "Type"},
                        "portionSize": 1,
                        "published": True,
                        "isDynamicType": value,
                        "isRepackable": value,
                    }
                }
            }
        ),
    )

    record = read.types(static_connection)[1]

    assert record.is_dynamic_type is value
    assert record.is_repackable is value


@pytest.mark.parametrize("value", [True, False, None])
def test_nullable_solar_flags_round_trip(
    static_connection: Connection, value: bool | None
) -> None:
    """Preserve all six nullable solar-system booleans with exact Python types."""
    write.map_regions(
        static_connection,
        dataset=ESD.MapRegionsDataset.model_validate(
            {
                "dataset": {
                    1: {
                        "constellationIDs": [2],
                        "name": {"en": "Region"},
                        "nebulaID": 1,
                        "position": {"x": 0, "y": 0, "z": 0},
                    }
                }
            }
        ),
    )
    write.map_constellations(
        static_connection,
        dataset=ESD.MapConstellationsDataset.model_validate(
            {
                "dataset": {
                    2: {
                        "name": {"en": "Constellation"},
                        "position": {"x": 0, "y": 0, "z": 0},
                        "regionID": 1,
                        "solarSystemIDs": [3],
                    }
                }
            }
        ),
    )
    flags = ("border", "corridor", "fringe", "hub", "international", "regional")
    write.map_solar_systems(
        static_connection,
        dataset=ESD.MapSolarSystemsDataset.model_validate(
            {
                "dataset": {
                    3: {
                        "constellationID": 2,
                        "regionID": 1,
                        "name": {"en": "System"},
                        "position": {"x": 1, "y": 2, "z": 3},
                        "radius": 4,
                        "securityStatus": 0.5,
                        **dict.fromkeys(flags, value),
                    }
                }
            }
        ),
    )

    record = read.map_solar_systems(static_connection)[3]

    for flag in flags:
        assert getattr(record, flag) is value, flag


_READERS = (
    "blueprints",
    "categories",
    "groups",
    "industry_activities",
    "map_constellations",
    "map_regions",
    "map_solar_systems",
    "market_groups",
    "meta_groups",
    "type_materials",
    "type_materials_randomized",
    "types",
    "sde_metadata",
)


def test_load_table_definitions() -> None:
    """The utility loads the packaged schema with foreign keys enabled."""
    from contextlib import closing
    from sqlite3 import connect

    with closing(connect(":memory:")) as connection:
        connection.executescript(util.load_table_definitions())
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert read.types(connection) == {}


def test_write_localized_categories(static_connection: Connection) -> None:
    """The public writer retains the helper's optional language selection."""
    write.categories(
        static_connection,
        dataset=ESD.CategoriesDataset(
            dataset={
                1: ESD.CategoriesRecord(
                    name=ESD.LocalizedString(en="Ships", de="Schiffe"),
                    published=True,
                )
            }
        ),
        language=LanguageEnum.DE,
    )

    assert read.categories(static_connection)[1].name == "Schiffe"


def test_metadata_placeholders_raise(static_connection: Connection) -> None:
    """Unimplemented generic metadata operations fail explicitly."""
    with pytest.raises(NotImplementedError, match="Metadata retrieval"):
        read.metadata(static_connection)
    with pytest.raises(NotImplementedError, match="metadata storage"):
        write.metadata(static_connection, metadata=object())


@pytest.mark.parametrize("name", [name for name in _READERS if name != "sde_metadata"])
def test_read_empty_dataset(name: str, static_connection: Connection) -> None:
    """An initialized database returns empty mappings, not fabricated records."""
    assert getattr(read, name)(static_connection) == {}


def test_missing_sde_metadata_raises(static_connection: Connection) -> None:
    """Missing build metadata is an error rather than an empty successful result."""
    with pytest.raises(ValueError, match="SDE metadata not found"):
        read.sde_metadata(static_connection)


@pytest.mark.parametrize("name", ["categories", "groups", "types"])
def test_publication_filter_round_trip(
    name: str, static_connection: Connection
) -> None:
    """Persist both publication states and filter only at read time."""
    if name == "categories":
        dataset = ESD.CategoriesDataset.model_validate(
            {
                "dataset": {
                    1: {"name": {"en": "Visible"}, "published": True},
                    2: {"name": {"en": "Hidden"}, "published": False},
                }
            }
        )
    elif name == "groups":
        write.categories(
            static_connection,
            dataset=ESD.CategoriesDataset.model_validate(
                {"dataset": {1: {"name": {"en": "Category"}, "published": True}}}
            ),
        )
        dataset = ESD.GroupsDataset.model_validate(
            {
                "dataset": {
                    key: {
                        "anchorable": False,
                        "anchored": False,
                        "categoryID": 1,
                        "fittableNonSingleton": True,
                        "name": {"en": label},
                        "published": published,
                        "useBasePrice": False,
                    }
                    for key, label, published in [
                        (1, "Visible", True),
                        (2, "Hidden", False),
                    ]
                }
            }
        )
    else:
        dataset = ESD.TypesDataset.model_validate(
            {
                "dataset": {
                    key: {
                        "groupID": 1,
                        "name": {"en": label},
                        "portionSize": 1,
                        "published": published,
                    }
                    for key, label, published in [
                        (1, "Visible", True),
                        (2, "Hidden", False),
                    ]
                }
            }
        )
    getattr(write, name)(static_connection, dataset=dataset)
    reader: Callable[..., dict[int, Any]] = getattr(read, name)

    published = reader(static_connection)
    all_records = reader(static_connection, only_published=False)

    assert set(published) == {1}
    assert set(all_records) == {1, 2}
    assert published[1].name == "Visible"
    assert published[1].published is True
    assert all_records[2].name == "Hidden"
    assert all_records[2].published is False


def test_materials_round_trip(static_connection: Connection) -> None:
    """Split fixed and randomized materials while retaining component quantities."""
    write.types(
        static_connection,
        dataset=ESD.TypesDataset.model_validate(
            {
                "dataset": {
                    key: {
                        "groupID": 1,
                        "name": {"en": str(key)},
                        "portionSize": 1,
                        "published": True,
                    }
                    for key in (1, 2, 3)
                }
            }
        ),
    )
    write.type_materials(
        static_connection,
        dataset=ESD.TypeMaterialsDataset.model_validate(
            {
                "dataset": {
                    1: {"materials": [{"materialTypeID": 3, "quantity": 10}]},
                    2: {
                        "randomizedMaterials": [
                            {"materialTypeID": 3, "quantityMin": 2, "quantityMax": 5}
                        ]
                    },
                    3: {},
                }
            }
        ),
    )

    assert read.type_materials(static_connection) == {
        1: ASM.TypeMaterialsRecord(
            type_id=1, materials=(ASM.Materials(material_type_id=3, quantity=10),)
        )
    }
    assert read.type_materials_randomized(static_connection) == {
        2: ASM.TypeMaterialsRandomizedRecord(
            type_id=2,
            materials=(
                ASM.RandomizedMaterials(
                    material_type_id=3, quantity_min=2, quantity_max=5
                ),
            ),
        )
    }


def test_sde_metadata_round_trip(static_connection: Connection) -> None:
    """Persist normalized build/release values without losing metadata."""
    source = SdeMetadata(
        buildNumber=3464040,
        releaseDate="2026-08-11T11:11:17Z",
        variant=SdeVariant.YAML,
        source_media=SourceMedia.DB,
    )
    write.sde_metadata(
        static_connection, dataset=ESD.SdeMetadataDataset(dataset=source)
    )

    assert read.sde_metadata(static_connection) == ASM.SdeMetadata(
        build_number=source.buildNumber, release_date=source.releaseDate
    )
