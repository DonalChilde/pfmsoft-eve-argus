"""Tests for static database query helpers."""

import json
import sqlite3

from pfmsoft.eve_argus.models.esd import esd_datasets as ESD
from pfmsoft.eve_argus.models.types import LanguageEnum
from pfmsoft.eve_argus.static.db import query_helpers


def _write_market_group_test_data(connection: sqlite3.Connection) -> None:
    types = ESD.TypesDataset(
        dataset={
            1001: ESD.TypesRecord(
                groupID=25,
                marketGroupID=101,
                name=ESD.LocalizedString(en="Rifter"),
                portionSize=1,
                published=True,
            ),
            1002: ESD.TypesRecord(
                groupID=25,
                marketGroupID=101,
                name=ESD.LocalizedString(en="Hidden Rifter"),
                portionSize=1,
                published=False,
            ),
            1003: ESD.TypesRecord(
                groupID=25,
                marketGroupID=102,
                name=ESD.LocalizedString(en="Wolf"),
                portionSize=1,
                published=True,
            ),
        }
    )
    market_groups = ESD.MarketGroupsDataset(
        dataset={
            102: ESD.MarketGroupsRecord(
                description=ESD.LocalizedString(
                    en="Assault Frigates", de="Sturmfregatten"
                ),
                hasTypes=True,
                iconID=None,
                name=ESD.LocalizedString(en="Assault Frigates", de="Sturmfregatten"),
                parentGroupID=101,
            ),
            100: ESD.MarketGroupsRecord(
                description=None,
                hasTypes=False,
                iconID=None,
                name=ESD.LocalizedString(en="Ships", de="Schiffe"),
                parentGroupID=None,
            ),
            101: ESD.MarketGroupsRecord(
                description=ESD.LocalizedString(en="Frigates", de="Fregatten"),
                hasTypes=True,
                iconID=42,
                name=ESD.LocalizedString(en="Frigates", de="Fregatten"),
                parentGroupID=100,
            ),
        }
    )
    query_helpers.write_types(connection, types)
    query_helpers.write_market_groups(
        connection, market_groups, language=LanguageEnum.DE
    )


def _make_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(query_helpers.load_table_definitions())
    return connection


def test_write_industry_activities_writes_string_fields() -> None:
    """Industrial activity records are written to the static database."""
    connection = _make_connection()
    dataset = ESD.IndustryActivitiesDataset(
        dataset={
            1: ESD.IndustryActivitiesRecord(
                description="Manufacturing of things",
                name="Manufacturing",
            )
        }
    )

    query_helpers.write_industry_activities(connection, dataset)

    activity = connection.execute(
        """
        SELECT activity_id, name, description
        FROM industry_activities
        """
    ).fetchone()

    assert activity == (1, "Manufacturing", "Manufacturing of things")


def test_write_market_groups_writes_localized_fields_and_parent() -> None:
    """Market group records are written to the static database."""
    connection = _make_connection()
    _write_market_group_test_data(connection)

    market_groups = connection.execute(
        """
        SELECT market_group_id, description, has_types, icon_id, name,
            parent_group_id, int_path, str_path, types
        FROM market_groups
        ORDER BY market_group_id
        """
    ).fetchall()

    assert [
        (
            market_group_id,
            description,
            has_types,
            icon_id,
            name,
            parent_group_id,
            json.loads(int_path),
            json.loads(str_path),
            json.loads(type_ids) if type_ids is not None else None,
        )
        for (
            market_group_id,
            description,
            has_types,
            icon_id,
            name,
            parent_group_id,
            int_path,
            str_path,
            type_ids,
        ) in market_groups
    ] == [
        (100, "NOT_DEFINED", 0, None, "Schiffe", None, [100], ["Schiffe"], None),
        (
            101,
            "Fregatten",
            1,
            42,
            "Fregatten",
            100,
            [100, 101],
            ["Schiffe", "Fregatten"],
            [1001],
        ),
        (
            102,
            "Sturmfregatten",
            1,
            None,
            "Sturmfregatten",
            101,
            [100, 101, 102],
            ["Schiffe", "Fregatten", "Sturmfregatten"],
            [1003],
        ),
    ]


def test_get_market_groups_returns_argus_static_records() -> None:
    """Market group rows are loaded into Argus static market group records."""
    connection = _make_connection()
    _write_market_group_test_data(connection)

    market_groups = query_helpers.get_market_groups(connection)

    assert market_groups[100].market_group_id == 100
    assert market_groups[100].description == "NOT_DEFINED"
    assert market_groups[100].has_types is False
    assert market_groups[100].icon_id is None
    assert market_groups[100].name == "Schiffe"
    assert market_groups[100].parent_group_id is None
    assert market_groups[100].int_path == (100,)
    assert market_groups[100].str_path == ("Schiffe",)
    assert market_groups[100].types == ()

    assert market_groups[101].market_group_id == 101
    assert market_groups[101].description == "Fregatten"
    assert market_groups[101].has_types is True
    assert market_groups[101].icon_id == 42
    assert market_groups[101].name == "Fregatten"
    assert market_groups[101].parent_group_id == 100
    assert market_groups[101].int_path == (100, 101)
    assert market_groups[101].str_path == ("Schiffe", "Fregatten")
    assert market_groups[101].types == (1001,)


def test_write_map_regions_writes_flattened_position_and_constellations() -> None:
    """Map region records are written to parent and child tables."""
    connection = _make_connection()
    dataset = ESD.MapRegionsDataset(
        dataset={
            10000002: ESD.MapRegionsRecord(
                constellationIDs=[20000020, 20000021],
                description=ESD.LocalizedString(en="The Forge", de="Die Schmiede"),
                factionID=500001,
                name=ESD.LocalizedString(en="The Forge", de="Die Schmiede"),
                nebulaID=123,
                position=ESD.Position(x=1.5, y=2.5, z=3.5),
                wormholeClassID=None,
            )
        }
    )

    query_helpers.write_map_regions(connection, dataset, language=LanguageEnum.DE)

    region = connection.execute(
        """
        SELECT region_id, description, faction_id, name, nebula_id,
            position_x, position_y, position_z, wormhole_class_id
        FROM map_regions
        """
    ).fetchone()
    constellations = connection.execute(
        """
        SELECT region_id, constellation_id
        FROM map_regions_constellations
        ORDER BY constellation_id
        """
    ).fetchall()

    assert region == (
        10000002,
        "Die Schmiede",
        500001,
        "Die Schmiede",
        123,
        1.5,
        2.5,
        3.5,
        None,
    )
    assert constellations == [(10000002, 20000020), (10000002, 20000021)]


def test_write_map_constellations_writes_flattened_position_and_solar_systems() -> None:
    """Map constellation records are written to parent and child tables."""
    connection = _make_connection()
    query_helpers.write_map_regions(
        connection,
        ESD.MapRegionsDataset(
            dataset={
                10000002: ESD.MapRegionsRecord(
                    constellationIDs=[],
                    description=None,
                    factionID=None,
                    name=ESD.LocalizedString(en="The Forge"),
                    nebulaID=123,
                    position=ESD.Position(x=1.0, y=2.0, z=3.0),
                    wormholeClassID=None,
                )
            }
        ),
    )
    dataset = ESD.MapConstellationsDataset(
        dataset={
            20000020: ESD.MapConstellationsRecord(
                factionID=None,
                name=ESD.LocalizedString(en="Kimotoro"),
                position=ESD.Position(x=4.5, y=5.5, z=6.5),
                regionID=10000002,
                solarSystemIDs=[30000142, 30000144],
                wormholeClassID=7,
            )
        }
    )

    query_helpers.write_map_constellations(connection, dataset)

    constellation = connection.execute(
        """
        SELECT constellation_id, faction_id, name, position_x, position_y,
            position_z, region_id, wormhole_class_id
        FROM map_constellations
        """
    ).fetchone()
    solar_systems = connection.execute(
        """
        SELECT constellation_id, solar_system_id
        FROM map_constellations_solar_systems
        ORDER BY solar_system_id
        """
    ).fetchall()

    assert constellation == (
        20000020,
        None,
        "Kimotoro",
        4.5,
        5.5,
        6.5,
        10000002,
        7,
    )
    assert solar_systems == [(20000020, 30000142), (20000020, 30000144)]


def test_write_map_solar_systems_writes_flattened_positions_and_lists() -> None:
    """Map solar system records are written to parent and child tables."""
    connection = _make_connection()
    query_helpers.write_categories(
        connection,
        ESD.CategoriesDataset(
            dataset={
                65: ESD.CategoriesRecord(
                    name=ESD.LocalizedString(en="Structure"), published=True
                )
            }
        ),
    )
    query_helpers.write_groups(
        connection,
        ESD.GroupsDataset(
            dataset={
                1404: ESD.GroupsRecord(
                    anchorable=False,
                    anchored=False,
                    categoryID=65,
                    fittableNonSingleton=False,
                    name=ESD.LocalizedString(en="Engineering Complex"),
                    published=True,
                    useBasePrice=False,
                )
            }
        ),
    )
    query_helpers.write_map_regions(
        connection,
        ESD.MapRegionsDataset(
            dataset={
                10000002: ESD.MapRegionsRecord(
                    constellationIDs=[],
                    description=None,
                    factionID=None,
                    name=ESD.LocalizedString(en="The Forge"),
                    nebulaID=123,
                    position=ESD.Position(x=1.0, y=2.0, z=3.0),
                    wormholeClassID=None,
                )
            }
        ),
    )
    query_helpers.write_map_constellations(
        connection,
        ESD.MapConstellationsDataset(
            dataset={
                20000020: ESD.MapConstellationsRecord(
                    factionID=None,
                    name=ESD.LocalizedString(en="Kimotoro"),
                    position=ESD.Position(x=4.0, y=5.0, z=6.0),
                    regionID=10000002,
                    solarSystemIDs=[],
                    wormholeClassID=None,
                )
            }
        ),
    )
    dataset = ESD.MapSolarSystemsDataset(
        dataset={
            30000142: ESD.MapSolarSystemsRecord(
                border=True,
                constellationID=20000020,
                corridor=False,
                disallowedAnchorCategories=[65],
                disallowedAnchorGroups=[1404],
                factionID=500001,
                fringe=None,
                hub=True,
                international=None,
                luminosity=0.99,
                name=ESD.LocalizedString(en="Jita", de="Jita DE"),
                planetIDs=[40009091, 40009092],
                position=ESD.Position(x=7.5, y=8.5, z=9.5),
                position2D=ESD.Position2D(x=10.5, y=11.5),
                radius=123456.0,
                regionID=10000002,
                regional=False,
                securityClass="B",
                securityStatus=0.945,
                starID=40009089,
                stargateIDs=[50000342],
                visualEffect="effectBeacon",
                wormholeClassID=None,
            )
        }
    )

    query_helpers.write_map_solar_systems(connection, dataset, language=LanguageEnum.DE)

    solar_system = connection.execute(
        """
        SELECT solar_system_id, border, constellation_id, corridor, faction_id,
            fringe, hub, international, luminosity, name, position_x, position_y,
            position_z, position2d_x, position2d_y, radius, region_id, regional,
            security_class, security_status, star_id, visual_effect, wormhole_class_id
        FROM map_solar_systems
        """
    ).fetchone()
    anchor_categories = connection.execute(
        "SELECT solar_system_id, category_id FROM map_solar_systems_disallowed_anchor_categories"
    ).fetchall()
    anchor_groups = connection.execute(
        "SELECT solar_system_id, group_id FROM map_solar_systems_disallowed_anchor_groups"
    ).fetchall()
    planets = connection.execute(
        "SELECT solar_system_id, planet_id FROM map_solar_systems_planets ORDER BY planet_id"
    ).fetchall()
    stargates = connection.execute(
        "SELECT solar_system_id, stargate_id FROM map_solar_systems_stargates"
    ).fetchall()

    assert solar_system == (
        30000142,
        1,
        20000020,
        0,
        500001,
        None,
        1,
        None,
        0.99,
        "Jita DE",
        7.5,
        8.5,
        9.5,
        10.5,
        11.5,
        123456.0,
        10000002,
        0,
        "B",
        0.945,
        40009089,
        "effectBeacon",
        None,
    )
    assert anchor_categories == [(30000142, 65)]
    assert anchor_groups == [(30000142, 1404)]
    assert planets == [(30000142, 40009091), (30000142, 40009092)]
    assert stargates == [(30000142, 50000342)]


def test_get_map_solar_systems_preserves_null_booleans() -> None:
    """Nullable solar-system booleans remain None when read from the database."""
    connection = _make_connection()
    connection.execute(
        """
        INSERT INTO map_regions (
            region_id, name, nebula_id, position_x, position_y, position_z
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (10000002, "The Forge", 123, 0, 0, 0),
    )
    connection.execute(
        """
        INSERT INTO map_constellations (
            constellation_id, name, position_x, position_y, position_z, region_id
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (20000020, "Kimotoro", 0, 0, 0, 10000002),
    )
    connection.execute(
        """
        INSERT INTO map_solar_systems (
            solar_system_id, border, constellation_id, corridor, fringe, hub,
            international, luminosity, name, position_x, position_y, position_z,
            radius, region_id, regional, security_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            30000142,
            None,
            20000020,
            None,
            None,
            None,
            None,
            None,
            "Jita",
            1,
            2,
            3,
            4,
            10000002,
            None,
            0.9,
        ),
    )

    record = query_helpers.get_map_solar_systems(connection)[30000142]

    assert record.border is None
    assert record.corridor is None
    assert record.fringe is None
    assert record.hub is None
    assert record.international is None
    assert record.regional is None
    assert record.disallowed_anchor_categories == ()
    assert record.disallowed_anchor_groups == ()
    assert record.planet_ids == ()
    assert record.stargate_ids == ()
