"""Tests for static database query helpers."""

import json
import sqlite3

from pfmsoft.eve_argus.models.esd import esd_datasets as ESD
from pfmsoft.eve_argus.models.types import LanguageEnum
from pfmsoft.eve_argus.static.db import query_helpers


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
    dataset = ESD.MarketGroupsDataset(
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

    query_helpers.write_market_groups(connection, dataset, language=LanguageEnum.DE)

    market_groups = connection.execute(
        """
        SELECT market_group_id, description, has_types, icon_id, name,
            parent_group_id, int_path, str_path
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
        ) in market_groups
    ] == [
        (100, "NOT_DEFINED", 0, None, "Schiffe", None, [100], ["Schiffe"]),
        (
            101,
            "Fregatten",
            1,
            42,
            "Fregatten",
            100,
            [100, 101],
            ["Schiffe", "Fregatten"],
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
        ),
    ]


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
