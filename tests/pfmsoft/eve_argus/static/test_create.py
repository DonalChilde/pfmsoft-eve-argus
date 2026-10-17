"""Test static database creation with a mocked ESD source and real SQLite."""

from sqlite3 import Connection
from unittest.mock import MagicMock

import pytest
from pfmsoft.eve_sd import EveSdDbQueryManager
from pfmsoft.eve_sd.helpers.sde_metadata import (
    SdeMetadata,
    SdeVariant,
    SourceMedia,
)

from pfmsoft.eve_argus.static import create, read


@pytest.fixture
def source_db() -> MagicMock:
    """Provide a small, internally consistent export without accessing live data."""
    datasets = {
        "types": {
            key: {
                "groupID": 1,
                "name": {"en": f"Type {key}"},
                "portionSize": 1,
                "published": True,
            }
            for key in (100, 101, 102)
        },
        "blueprints": {
            100: {
                "blueprintTypeID": 100,
                "activities": {
                    "manufacturing": {
                        "time": 60,
                        "materials": [{"typeID": 102, "quantity": 10}],
                        "products": [{"typeID": 101, "quantity": 1}],
                    }
                },
            }
        },
        "typeMaterials": {101: {"materials": [{"materialTypeID": 102, "quantity": 5}]}},
        "metaGroups": {1: {"name": {"en": "Tech I"}}},
        "categories": {1: {"name": {"en": "Category"}, "published": True}},
        "groups": {
            1: {
                "anchorable": False,
                "anchored": False,
                "categoryID": 1,
                "fittableNonSingleton": False,
                "name": {"en": "Group"},
                "published": True,
                "useBasePrice": False,
            }
        },
        "industryActivities": {
            1: {"name": "Manufacturing", "description": "Make things"}
        },
        "mapRegions": {
            1: {
                "constellationIDs": [2],
                "name": {"en": "Region"},
                "nebulaID": 1,
                "position": {"x": 0, "y": 0, "z": 0},
            }
        },
        "mapConstellations": {
            2: {
                "name": {"en": "Constellation"},
                "position": {"x": 0, "y": 0, "z": 0},
                "regionID": 1,
                "solarSystemIDs": [3],
            }
        },
        "mapSolarSystems": {
            3: {
                "constellationID": 2,
                "name": {"en": "System"},
                "position": {"x": 0, "y": 0, "z": 0},
                "radius": 1,
                "regionID": 1,
                "securityStatus": 0.9,
            }
        },
        "marketGroups": {1: {"hasTypes": False, "name": {"en": "Market"}}},
    }
    db = MagicMock(spec=EveSdDbQueryManager)
    db.query.get_int_records.side_effect = lambda name: iter(datasets[name].items())
    db.query.sde_metadata = SdeMetadata(
        buildNumber=123,
        releaseDate="2026-08-11T11:11:17Z",
        variant=SdeVariant.YAML,
        source_media=SourceMedia.DB,
    )
    return db


def test_is_empty_with_no_metadata(static_connection: Connection) -> None:
    """An initialized but unpopulated schema is eligible for import."""
    assert create._is_empty(static_connection) is True


def test_create_db_imports_related_records(
    static_connection: Connection, source_db: MagicMock
) -> None:
    """Import dependencies before their children without disabling foreign keys."""
    create.create_db(static_connection, source_db)

    assert set(read.types(static_connection)) == {100, 101, 102}
    assert set(read.categories(static_connection)) == {1}
    assert set(read.groups(static_connection)) == {1}
    assert set(read.map_regions(static_connection)) == {1}
    assert set(read.map_constellations(static_connection)) == {2}
    assert set(read.map_solar_systems(static_connection)) == {3}
    assert set(read.meta_groups(static_connection)) == {1}
    assert set(read.market_groups(static_connection)) == {1}
    assert set(read.type_materials(static_connection)) == {101}
    assert set(read.industry_activities(static_connection)) == {1}
    assert read.sde_metadata(static_connection).build_number == 123
    assert static_connection.execute(
        "SELECT blueprint_type_id FROM blueprints"
    ).fetchall() == [(100,)]
    assert static_connection.execute(
        "SELECT material_type_id, quantity FROM blueprint_activity_materials"
    ).fetchall() == [(102, 10)]
    assert static_connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert create._is_empty(static_connection) is False


def test_create_db_rejects_existing_build(
    static_connection: Connection, source_db: MagicMock
) -> None:
    """Reject an already imported database before querying or altering anything."""
    static_connection.execute(
        "INSERT INTO sde_metadata VALUES (?, ?)", (123, "release")
    )

    with pytest.raises(RuntimeError, match="not empty"):
        create.create_db(static_connection, source_db)

    source_db.query.get_int_records.assert_not_called()
    assert static_connection.execute("SELECT * FROM sde_metadata").fetchall() == [
        (123, "release")
    ]


def test_create_db_propagates_source_failure(
    static_connection: Connection, source_db: MagicMock
) -> None:
    """Do not report success or write build metadata if loading fails."""
    source_db.query.get_int_records.side_effect = ValueError("invalid source")

    with pytest.raises(ValueError, match="invalid source"):
        create.create_db(static_connection, source_db)

    with pytest.raises(ValueError, match="SDE metadata not found"):
        read.sde_metadata(static_connection)
