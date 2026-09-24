"""Query helpers for interacting with the EVE Argus static database."""

import json
import logging
import sqlite3
from dataclasses import asdict
from typing import cast

from pfmsoft.eve_argus.helpers.package_resource import load_package_resouce_text
from pfmsoft.eve_argus.helpers.timing import log_timing
from pfmsoft.eve_argus.models.argus import static as ASM
from pfmsoft.eve_argus.models.esd import esd_datasets as ESD
from pfmsoft.eve_argus.models.types import LanguageEnum

logger = logging.getLogger(__name__)

_table_def_parent = "pfmsoft.eve_argus.static.db"
_table_def_file = "table_definitions.sql"
_timing_log_level = logging.INFO


def load_table_definitions() -> str:
    """Load the SQL table definitions for the market orders database."""
    return load_package_resouce_text(_table_def_parent, _table_def_file)


####### WRITE db queries #######


@log_timing(logger=logger, level=_timing_log_level)
def write_types(
    connection: sqlite3.Connection,
    types: ESD.TypesDataset,
    language: LanguageEnum = LanguageEnum.EN,
) -> None:
    """Write the types dataset to the database."""
    with connection:
        connection.executemany(
            """
            INSERT INTO types (
                type_id, base_price, capacity, description, faction_id,
                graphic_id, group_id, icon_id, market_group_id, mass,
                meta_group_id, meta_level, name, packaged_volume, portion_size,
                published, race_id, radius, ship_tree_group_id, sound_id,
                tech_level, variation_parent_type_id, volume
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    type_id,
                    record.basePrice,
                    record.capacity,
                    record.description_localized(language),
                    record.factionID,
                    record.graphicID,
                    record.groupID,
                    record.iconID,
                    record.marketGroupID,
                    record.mass,
                    record.metaGroupID,
                    record.metaLevel,
                    record.name_localized(language),
                    record.packagedVolume,
                    record.portionSize,
                    record.published,
                    record.raceID,
                    record.radius,
                    record.shipTreeGroupID,
                    record.soundID,
                    record.techLevel,
                    record.variationParentTypeID,
                    record.volume,
                )
                for type_id, record in types.dataset.items()
            ),
        )
    logger.info("wrote %d types records to the database", len(types.dataset))


@log_timing(logger=logger, level=_timing_log_level)
def write_meta_groups(
    connection: sqlite3.Connection,
    meta_groups: ESD.MetaGroupsDataset,
    language: LanguageEnum = LanguageEnum.EN,
) -> None:
    """Write the meta groups dataset to the database."""
    with connection:
        connection.executemany(
            """
            INSERT INTO meta_groups (
                meta_group_id, color, description, icon_id, icon_suffix, name
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    meta_group_id,
                    json.dumps(asdict(record.color)) if record.color else None,
                    record.description_localized(language),
                    record.iconID,
                    record.iconSuffix,
                    record.name_localized(language),
                )
                for meta_group_id, record in meta_groups.dataset.items()
            ),
        )
    logger.info(
        "wrote %d meta groups records to the database", len(meta_groups.dataset)
    )


@log_timing(logger=logger, level=_timing_log_level)
def write_type_materials(
    connection: sqlite3.Connection,
    type_materials: ESD.TypeMaterialsDataset,
) -> None:
    """Write the type materials dataset to the database."""
    with connection:
        connection.executemany(
            "INSERT INTO type_materials (type_id) VALUES (?)",
            ((type_id,) for type_id in type_materials.dataset),
        )
        connection.executemany(
            """
            INSERT INTO type_material_components (type_id, material_type_id, quantity)
            VALUES (?, ?, ?)
            """,
            (
                (type_id, material.materialTypeID, material.quantity)
                for type_id, record in type_materials.dataset.items()
                for material in record.materials or []
            ),
        )
        connection.executemany(
            """
            INSERT INTO type_material_randomized_components (
                type_id, material_type_id, quantity_min, quantity_max
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                (
                    type_id,
                    material.materialTypeID,
                    material.quantityMin,
                    material.quantityMax,
                )
                for type_id, record in type_materials.dataset.items()
                for material in record.randomized_materials or []
            ),
        )
    logger.info(
        "wrote %d type materials records to the database", len(type_materials.dataset)
    )


@log_timing(logger=logger, level=_timing_log_level)
def write_categories(
    connection: sqlite3.Connection,
    categories: ESD.CategoriesDataset,
    language: LanguageEnum = LanguageEnum.EN,
) -> None:
    """Write the categories dataset to the database."""
    with connection:
        connection.executemany(
            """
            INSERT INTO categories (category_id, icon_id, name, published)
            VALUES (?, ?, ?, ?)
            """,
            (
                (
                    category_id,
                    record.iconID,
                    record.name_localized(language),
                    record.published,
                )
                for category_id, record in categories.dataset.items()
            ),
        )
    logger.info("wrote %d categories records to the database", len(categories.dataset))


@log_timing(logger=logger, level=_timing_log_level)
def write_groups(
    connection: sqlite3.Connection,
    groups: ESD.GroupsDataset,
    language: LanguageEnum = LanguageEnum.EN,
) -> None:
    """Write the groups dataset to the database."""
    with connection:
        connection.executemany(
            """
            INSERT INTO groups (
                group_id, anchorable, anchored, category_id,
                fittable_non_singleton, icon_id, name, published, use_base_price
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    group_id,
                    record.anchorable,
                    record.anchored,
                    record.categoryID,
                    record.fittableNonSingleton,
                    record.iconID,
                    record.name_localized(language),
                    record.published,
                    record.useBasePrice,
                )
                for group_id, record in groups.dataset.items()
            ),
        )
    logger.info("wrote %d groups records to the database", len(groups.dataset))


@log_timing(logger=logger, level=_timing_log_level)
def write_market_groups(
    connection: sqlite3.Connection,
    market_groups: ESD.MarketGroupsDataset,
    language: LanguageEnum = LanguageEnum.EN,
) -> None:
    """Write the market groups dataset to the database."""
    sorted_group_ids: list[int] = []
    visited_group_ids: set[int] = set()

    def visit(market_group_id: int) -> None:
        if market_group_id in visited_group_ids:
            return
        record = market_groups.dataset[market_group_id]
        if record.parentGroupID in market_groups.dataset:
            visit(record.parentGroupID)
        visited_group_ids.add(market_group_id)
        sorted_group_ids.append(market_group_id)

    for market_group_id in market_groups.dataset:
        visit(market_group_id)

    path_rows = _get_market_path_rows(market_groups, sorted_group_ids, language)
    type_ids_by_market_group_id = _get_published_type_ids_by_market_group_id(connection)

    with connection:
        connection.executemany(
            """
            INSERT INTO market_groups (
                market_group_id, description, has_types, icon_id, name,
                parent_group_id, int_path, str_path, types
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    market_group_id,
                    record.description_localized(language),
                    record.hasTypes,
                    record.iconID,
                    record.name_localized(language),
                    record.parentGroupID,
                    int_path,
                    str_path,
                    json.dumps(type_ids)
                    if (type_ids := type_ids_by_market_group_id.get(market_group_id))
                    else None,
                )
                for market_group_id, int_path, str_path in path_rows
                if (record := market_groups.dataset[market_group_id])
            ),
        )
    logger.info(
        "wrote %d market groups records to the database", len(market_groups.dataset)
    )


def _get_published_type_ids_by_market_group_id(
    connection: sqlite3.Connection,
) -> dict[int, tuple[int, ...]]:
    rows = connection.execute(
        """
        SELECT market_group_id, type_id
        FROM types
        WHERE published = 1 AND market_group_id IS NOT NULL
        ORDER BY market_group_id, type_id
        """
    ).fetchall()
    type_ids_by_market_group_id: dict[int, list[int]] = {}
    for market_group_id, type_id in rows:
        type_ids_by_market_group_id.setdefault(market_group_id, []).append(type_id)
    return {
        market_group_id: tuple(type_ids)
        for market_group_id, type_ids in type_ids_by_market_group_id.items()
    }


def _get_market_path_rows(
    market_groups: ESD.MarketGroupsDataset,
    sorted_group_ids: list[int],
    language: LanguageEnum,
) -> list[tuple[int, str, str]]:
    int_paths: dict[int, tuple[int, ...]] = {}
    str_paths: dict[int, tuple[str, ...]] = {}

    for market_group_id in sorted_group_ids:
        record = market_groups.dataset[market_group_id]
        parent_int_path: tuple[int, ...] = ()
        parent_str_path: tuple[str, ...] = ()
        if record.parentGroupID is not None:
            parent_int_path = int_paths.get(record.parentGroupID, ())
            parent_str_path = str_paths.get(record.parentGroupID, ())
        int_paths[market_group_id] = (*parent_int_path, market_group_id)
        str_paths[market_group_id] = (
            *parent_str_path,
            record.name_localized(language),
        )

    return [
        (
            market_group_id,
            json.dumps(int_paths[market_group_id]),
            json.dumps(str_paths[market_group_id]),
        )
        for market_group_id in sorted_group_ids
    ]


def _get_valid_blueprint_ids(
    connection: sqlite3.Connection,
    blueprints: ESD.BlueprintsDataset,
) -> set[int]:
    """Return blueprint IDs whose records satisfy the database constraints.

    Only blueprint records that are published and have all required types present
    in the database are considered valid.
    """
    type_publication = {
        type_id: published
        for type_id, published in connection.execute(
            "SELECT type_id, published FROM types"
        )
    }
    valid_blueprint_ids: set[int] = set()
    activity_names = (
        "copying",
        "invention",
        "manufacturing",
        "reaction",
        "research_material",
        "research_time",
    )

    for blueprint_type_id, record in blueprints.dataset.items():
        failure_reasons: set[str] = set()
        if blueprint_type_id not in type_publication:
            failure_reasons.add("missing blueprint type")
        is_published = type_publication.get(blueprint_type_id, False)

        type_ids = type_publication.keys()

        for activity_name in activity_names:
            activity = getattr(record.activities, activity_name)
            if activity is None:
                continue
            activity = cast(ESD.Blueprint_Activity, activity)
            if any(
                material.typeID not in type_ids for material in activity.materials or []
            ):
                failure_reasons.add("missing material type")
            if any(skill.typeID not in type_ids for skill in activity.skills or []):
                failure_reasons.add("missing skill type")
            if any(
                product.typeID not in type_ids for product in activity.products or []
            ):
                failure_reasons.add("missing product type")

        if failure_reasons and not is_published:
            failure_reasons.add("unpublished blueprint type")
        if failure_reasons:
            logger.warning(
                "Skipping invalid blueprint record: blueprint_type_id=%s "
                "reasons=%s record=%r",
                blueprint_type_id,
                ", ".join(sorted(failure_reasons)),
                asdict(record),
            )
            continue
        if not is_published:
            continue
        valid_blueprint_ids.add(blueprint_type_id)

    return valid_blueprint_ids


@log_timing(logger=logger, level=_timing_log_level)
def write_blueprints(
    connection: sqlite3.Connection,
    blueprints: ESD.BlueprintsDataset,
) -> None:
    """Write the blueprints dataset to the database."""
    with connection:
        valid_blueprint_ids = _get_valid_blueprint_ids(connection, blueprints)
        valid_blueprints = {
            blueprint_type_id: record
            for blueprint_type_id, record in blueprints.dataset.items()
            if blueprint_type_id in valid_blueprint_ids
        }
        connection.executemany(
            """
            INSERT INTO blueprints (blueprint_type_id, max_production_limit)
            VALUES (?, ?)
            """,
            (
                (blueprint_type_id, record.maxProductionLimit)
                for blueprint_type_id, record in valid_blueprints.items()
            ),
        )

        activity_rows = [
            (blueprint_type_id, activity_name, activity.time)
            for blueprint_type_id, record in valid_blueprints.items()
            for activity_name in (
                "copying",
                "invention",
                "manufacturing",
                "reaction",
                "research_material",
                "research_time",
            )
            if (activity := getattr(record.activities, activity_name)) is not None
        ]
        connection.executemany(
            """
            INSERT INTO blueprint_activities (blueprint_type_id, activity, time)
            VALUES (?, ?, ?)
            """,
            activity_rows,
        )

        material_rows: list[tuple[int, str, int, int]] = []
        for blueprint_type_id, record in valid_blueprints.items():
            for activity_name in (
                "copying",
                "invention",
                "manufacturing",
                "reaction",
                "research_material",
                "research_time",
            ):
                activity = getattr(record.activities, activity_name)
                if activity is None:
                    continue
                activity = cast(ESD.Blueprint_Activity, activity)
                for material in activity.materials or []:
                    material_rows.append((
                        blueprint_type_id,
                        activity_name,
                        material.typeID,
                        material.quantity,
                    ))

        connection.executemany(
            """
            INSERT INTO blueprint_activity_materials (
                blueprint_type_id, activity, material_type_id, quantity
            )
            VALUES (?, ?, ?, ?)
            """,
            material_rows,
        )

        skill_rows: dict[tuple[int, str, int], tuple[int, str, int, int]] = {}
        for blueprint_type_id, record in valid_blueprints.items():
            for activity_name in (
                "copying",
                "invention",
                "manufacturing",
                "reaction",
                "research_material",
                "research_time",
            ):
                activity = getattr(record.activities, activity_name)
                if activity is None:
                    continue
                activity = cast(ESD.Blueprint_Activity, activity)
                for skill in activity.skills or []:
                    skill_key = (blueprint_type_id, activity_name, skill.typeID)
                    skill_rows[skill_key] = (
                        blueprint_type_id,
                        activity_name,
                        skill.typeID,
                        skill.level,
                    )

        product_rows: list[tuple[int, str, int, int, float | None]] = []
        for blueprint_type_id, record in valid_blueprints.items():
            for activity_name in (
                "copying",
                "invention",
                "manufacturing",
                "reaction",
                "research_material",
                "research_time",
            ):
                activity = getattr(record.activities, activity_name)
                if activity is None:
                    continue
                activity = cast(ESD.Blueprint_Activity, activity)
                for product in activity.products or []:
                    product_rows.append((
                        blueprint_type_id,
                        activity_name,
                        product.typeID,
                        product.quantity,
                        product.probability,
                    ))

        connection.executemany(
            """
            INSERT INTO blueprint_activity_skills (
                blueprint_type_id, activity, skill_type_id, level
            )
            VALUES (?, ?, ?, ?)
            """,
            skill_rows.values(),
        )

        connection.executemany(
            """
            INSERT INTO blueprint_activity_products (
                blueprint_type_id, activity, product_type_id, quantity, probability
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            product_rows,
        )
    logger.info("wrote %d valid blueprints to the database", len(valid_blueprints))


@log_timing(logger=logger, level=_timing_log_level)
def write_map_regions(
    connection: sqlite3.Connection,
    map_regions: ESD.MapRegionsDataset,
    language: LanguageEnum = LanguageEnum.EN,
) -> None:
    """Write the map regions dataset to the database."""
    with connection:
        connection.executemany(
            """
            INSERT INTO map_regions (
                region_id, description, faction_id, name, nebula_id,
                position_x, position_y, position_z, wormhole_class_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    region_id,
                    record.description_localized(language),
                    record.factionID,
                    record.name_localized(language),
                    record.nebulaID,
                    record.position.x,
                    record.position.y,
                    record.position.z,
                    record.wormholeClassID,
                )
                for region_id, record in map_regions.dataset.items()
            ),
        )
        connection.executemany(
            """
            INSERT INTO map_regions_constellations (region_id, constellation_id)
            VALUES (?, ?)
            """,
            (
                (region_id, constellation_id)
                for region_id, record in map_regions.dataset.items()
                for constellation_id in record.constellationIDs
            ),
        )
    logger.info("wrote %d map regions to the database", len(map_regions.dataset))


@log_timing(logger=logger, level=_timing_log_level)
def write_map_constellations(
    connection: sqlite3.Connection,
    map_constellations: ESD.MapConstellationsDataset,
    language: LanguageEnum = LanguageEnum.EN,
) -> None:
    """Write the map constellations dataset to the database."""
    with connection:
        connection.executemany(
            """
            INSERT INTO map_constellations (
                constellation_id, faction_id, name, position_x, position_y,
                position_z, region_id, wormhole_class_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    constellation_id,
                    record.factionID,
                    record.name_localized(language),
                    record.position.x,
                    record.position.y,
                    record.position.z,
                    record.regionID,
                    record.wormholeClassID,
                )
                for constellation_id, record in map_constellations.dataset.items()
            ),
        )
        connection.executemany(
            """
            INSERT INTO map_constellations_solar_systems (
                constellation_id, solar_system_id
            )
            VALUES (?, ?)
            """,
            (
                (constellation_id, solar_system_id)
                for constellation_id, record in map_constellations.dataset.items()
                for solar_system_id in record.solarSystemIDs
            ),
        )
    logger.info(
        "wrote %d map constellations to the database", len(map_constellations.dataset)
    )


@log_timing(logger=logger, level=_timing_log_level)
def write_map_solar_systems(
    connection: sqlite3.Connection,
    map_solar_systems: ESD.MapSolarSystemsDataset,
    language: LanguageEnum = LanguageEnum.EN,
) -> None:
    """Write the map solar systems dataset to the database."""
    with connection:
        connection.executemany(
            """
            INSERT INTO map_solar_systems (
                solar_system_id, border, constellation_id, corridor, faction_id,
                fringe, hub, international, luminosity, name, position_x,
                position_y, position_z, position2d_x, position2d_y, radius,
                region_id, regional, security_class, security_status, star_id,
                visual_effect, wormhole_class_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    solar_system_id,
                    record.border,
                    record.constellationID,
                    record.corridor,
                    record.factionID,
                    record.fringe,
                    record.hub,
                    record.international,
                    record.luminosity,
                    getattr(record.name, language, record.name.en),
                    record.position.x,
                    record.position.y,
                    record.position.z,
                    record.position2D.x if record.position2D else None,
                    record.position2D.y if record.position2D else None,
                    record.radius,
                    record.regionID,
                    record.regional,
                    record.securityClass,
                    record.securityStatus,
                    record.starID,
                    record.visualEffect,
                    record.wormholeClassID,
                )
                for solar_system_id, record in map_solar_systems.dataset.items()
            ),
        )
        connection.executemany(
            """
            INSERT INTO map_solar_systems_disallowed_anchor_categories (
                solar_system_id, category_id
            )
            VALUES (?, ?)
            """,
            (
                (solar_system_id, category_id)
                for solar_system_id, record in map_solar_systems.dataset.items()
                for category_id in record.disallowedAnchorCategories or []
            ),
        )
        connection.executemany(
            """
            INSERT INTO map_solar_systems_disallowed_anchor_groups (
                solar_system_id, group_id
            )
            VALUES (?, ?)
            """,
            (
                (solar_system_id, group_id)
                for solar_system_id, record in map_solar_systems.dataset.items()
                for group_id in record.disallowedAnchorGroups or []
            ),
        )
        connection.executemany(
            """
            INSERT INTO map_solar_systems_planets (solar_system_id, planet_id)
            VALUES (?, ?)
            """,
            (
                (solar_system_id, planet_id)
                for solar_system_id, record in map_solar_systems.dataset.items()
                for planet_id in record.planetIDs or []
            ),
        )
        connection.executemany(
            """
            INSERT INTO map_solar_systems_stargates (solar_system_id, stargate_id)
            VALUES (?, ?)
            """,
            (
                (solar_system_id, stargate_id)
                for solar_system_id, record in map_solar_systems.dataset.items()
                for stargate_id in record.stargateIDs or []
            ),
        )
    logger.info(
        "wrote %d map solar systems to the database", len(map_solar_systems.dataset)
    )


@log_timing(logger=logger, level=_timing_log_level)
def write_industry_activities(
    connection: sqlite3.Connection,
    industrial_activities: ESD.IndustryActivitiesDataset,
) -> None:
    """Write the industrial activities dataset to the database."""
    with connection:
        connection.executemany(
            """
            INSERT INTO industry_activities (activity_id, name, description)
            VALUES (?, ?, ?)
            """,
            (
                (
                    activity_id,
                    record.name,
                    record.description,
                )
                for activity_id, record in industrial_activities.dataset.items()
            ),
        )
    logger.info(
        "wrote %d industry activities to the database",
        len(industrial_activities.dataset),
    )


######### GET db queries #########


@log_timing(logger=logger, level=_timing_log_level)
def get_market_groups(connection: sqlite3.Connection) -> ASM.MarketGroupsDataset:
    """Retrieve all market groups from the database."""
    rows = connection.execute(
        """
        SELECT
            market_group_id,
            name,
            description,
            parent_group_id,
            has_types,
            icon_id,
            int_path,
            str_path,
            types
        FROM market_groups
        ORDER BY market_group_id
        """
    ).fetchall()
    result = {
        market_group_id: ASM.MarketGroupsRecord(
            market_group_id=market_group_id,
            name=name,
            description=description,
            parent_group_id=parent_group_id,
            has_types=bool(has_types),
            icon_id=icon_id,
            int_path=tuple(json.loads(int_path)),
            str_path=tuple(json.loads(str_path)),
            types=tuple(json.loads(types)) if types is not None else (),
        )
        for (
            market_group_id,
            name,
            description,
            parent_group_id,
            has_types,
            icon_id,
            int_path,
            str_path,
            types,
        ) in rows
    }
    logger.info("Retrieved %d market groups", len(result))
    return result


@log_timing(logger=logger, level=_timing_log_level)
def get_industry_activities(
    connection: sqlite3.Connection,
) -> ASM.IndustryActivityDataset:
    """Retrieve all industry activities from the database."""
    rows = connection.execute(
        """
        SELECT
            activity_id,
            name,
            description
        FROM industry_activities
        ORDER BY activity_id
        """
    ).fetchall()
    result = {
        activity_id: ASM.IndustryActivityRecord(
            activity_id=activity_id,
            name=name,
            description=description,
        )
        for activity_id, name, description in rows
    }
    logger.info("Retrieved %d industry activities", len(result))
    return result


@log_timing(logger=logger, level=_timing_log_level)
def get_map_regions(
    connection: sqlite3.Connection,
) -> ASM.MapRegionsDataset:
    """Retrieve all map regions from the database."""
    rows = connection.execute(
        """
        SELECT
            region_id,
            description,
            faction_id,
            name,
            nebula_id,
            position_x,
            position_y,
            position_z,
            wormhole_class_id
        FROM map_regions
        ORDER BY region_id
        """
    ).fetchall()
    constellation_ids_by_region_id: dict[int, list[int]] = {}
    for region_id, constellation_id in connection.execute(
        """
        SELECT region_id, constellation_id
        FROM map_regions_constellations
        ORDER BY region_id, constellation_id
        """
    ):
        constellation_ids_by_region_id.setdefault(region_id, []).append(
            constellation_id
        )

    result = {
        region_id: ASM.MapRegionsRecord(
            region_id=region_id,
            constellation_ids=tuple(constellation_ids_by_region_id.get(region_id, ())),
            description=description,
            faction_id=faction_id,
            name=name,
            nebula_id=nebula_id,
            position_x=position_x,
            position_y=position_y,
            position_z=position_z,
            wormhole_class_id=wormhole_class_id,
        )
        for (
            region_id,
            description,
            faction_id,
            name,
            nebula_id,
            position_x,
            position_y,
            position_z,
            wormhole_class_id,
        ) in rows
    }
    logger.info("Retrieved %d map regions", len(result))
    return result


@log_timing(logger=logger, level=_timing_log_level)
def get_map_constellations(
    connection: sqlite3.Connection,
) -> ASM.MapConstellationsDataset:
    """Retrieve all map constellations from the database."""
    rows = connection.execute(
        """
        SELECT
            constellation_id,
            faction_id,
            name,
            position_x,
            position_y,
            position_z,
            region_id,
            wormhole_class_id
        FROM map_constellations
        ORDER BY constellation_id
        """
    ).fetchall()
    solar_system_ids_by_constellation_id: dict[int, list[int]] = {}
    for constellation_id, solar_system_id in connection.execute(
        """
        SELECT constellation_id, solar_system_id
        FROM map_constellations_solar_systems
        ORDER BY constellation_id, solar_system_id
        """
    ):
        solar_system_ids_by_constellation_id.setdefault(constellation_id, []).append(
            solar_system_id
        )

    result = {
        constellation_id: ASM.MapConstellationsRecord(
            constellation_id=constellation_id,
            faction_id=faction_id,
            name=name,
            position_x=position_x,
            position_y=position_y,
            position_z=position_z,
            region_id=region_id,
            solar_system_ids=tuple(
                solar_system_ids_by_constellation_id.get(constellation_id, ())
            ),
            wormhole_class_id=wormhole_class_id,
        )
        for (
            constellation_id,
            faction_id,
            name,
            position_x,
            position_y,
            position_z,
            region_id,
            wormhole_class_id,
        ) in rows
    }
    logger.info("Retrieved %d map constellations", len(result))
    return result


@log_timing(logger=logger, level=_timing_log_level)
def get_map_solar_systems(
    connection: sqlite3.Connection,
) -> ASM.MapSolarSystemsDataset:
    """Retrieve all map systems from the database."""
    rows = connection.execute(
        """
        SELECT
            solar_system_id,
            border,
            constellation_id,
            corridor,
            faction_id,
            fringe,
            hub,
            international,
            luminosity,
            name,
            position_x,
            position_y,
            position_z,
            position2d_x,
            position2d_y,
            radius,
            region_id,
            regional,
            security_class,
            security_status,
            star_id,
            visual_effect,
            wormhole_class_id
        FROM map_solar_systems
        ORDER BY solar_system_id
        """
    ).fetchall()

    def get_ids_by_system_id(
        table_name: str, column_name: str
    ) -> dict[int, tuple[int, ...]]:
        ids_by_system_id: dict[int, list[int]] = {}
        for solar_system_id, child_id in connection.execute(
            f"""
            SELECT solar_system_id, {column_name}
            FROM {table_name}
            ORDER BY solar_system_id, {column_name}
            """
        ):
            ids_by_system_id.setdefault(solar_system_id, []).append(child_id)
        return {
            solar_system_id: tuple(child_ids)
            for solar_system_id, child_ids in ids_by_system_id.items()
        }

    disallowed_categories = get_ids_by_system_id(
        "map_solar_systems_disallowed_anchor_categories", "category_id"
    )
    disallowed_groups = get_ids_by_system_id(
        "map_solar_systems_disallowed_anchor_groups", "group_id"
    )
    planet_ids = get_ids_by_system_id("map_solar_systems_planets", "planet_id")
    stargate_ids = get_ids_by_system_id("map_solar_systems_stargates", "stargate_id")

    result = {
        solar_system_id: ASM.MapSolarSystemsRecord(
            solar_system_id=solar_system_id,
            border=border,
            constellation_id=constellation_id,
            corridor=corridor,
            disallowed_anchor_categories=disallowed_categories.get(solar_system_id, ()),
            disallowed_anchor_groups=disallowed_groups.get(solar_system_id, ()),
            faction_id=faction_id,
            fringe=fringe,
            hub=hub,
            international=international,
            luminosity=luminosity,
            name=name,
            planet_ids=planet_ids.get(solar_system_id, ()),
            position_x=position_x,
            position_y=position_y,
            position_z=position_z,
            position2d_x=position2d_x,
            position2d_y=position2d_y,
            radius=radius,
            region_id=region_id,
            regional=regional,
            security_class=security_class,
            security_status=security_status,
            star_id=star_id,
            stargate_ids=stargate_ids.get(solar_system_id, ()),
            visual_effect=visual_effect,
            wormhole_class_id=wormhole_class_id,
        )
        for (
            solar_system_id,
            border,
            constellation_id,
            corridor,
            faction_id,
            fringe,
            hub,
            international,
            luminosity,
            name,
            position_x,
            position_y,
            position_z,
            position2d_x,
            position2d_y,
            radius,
            region_id,
            regional,
            security_class,
            security_status,
            star_id,
            visual_effect,
            wormhole_class_id,
        ) in rows
    }
    logger.info("Retrieved %d map solar systems", len(result))
    return result


@log_timing(logger=logger, level=_timing_log_level)
def get_groups(
    connection: sqlite3.Connection, only_published: bool = True
) -> ASM.GroupsDataset:
    """Retrieve all groups from the database."""
    where_clause = "WHERE published = 1" if only_published else ""
    rows = connection.execute(
        f"""
        SELECT
            group_id,
            anchorable,
            anchored,
            category_id,
            fittable_non_singleton,
            icon_id,
            name,
            published,
            use_base_price
        FROM groups
        {where_clause}
        ORDER BY group_id
        """
    ).fetchall()
    result = {
        group_id: ASM.GroupsRecord(
            group_id=group_id,
            anchorable=bool(anchorable),
            anchored=bool(anchored),
            category_id=category_id,
            fittable_non_singleton=bool(fittable_non_singleton),
            icon_id=icon_id,
            name=name,
            published=bool(published),
            use_base_price=bool(use_base_price),
        )
        for (
            group_id,
            anchorable,
            anchored,
            category_id,
            fittable_non_singleton,
            icon_id,
            name,
            published,
            use_base_price,
        ) in rows
    }
    logger.info("Retrieved %d groups", len(result))
    return result


@log_timing(logger=logger, level=_timing_log_level)
def get_categories(
    connection: sqlite3.Connection, only_published: bool = True
) -> ASM.CategoriesDataset:
    """Retrieve all categories from the database."""
    ...


@log_timing(logger=logger, level=_timing_log_level)
def get_type_materials(
    connection: sqlite3.Connection,
) -> ASM.TypeMaterialsDataset:
    """Retrieve all type materials from the database."""
    ...


@log_timing(logger=logger, level=_timing_log_level)
def get_type_materials_randomized(
    connection: sqlite3.Connection,
) -> ASM.TypeMaterialsRandomizedDataset:
    """Retrieve all type materials from the database in randomized order."""
    ...


@log_timing(logger=logger, level=_timing_log_level)
def get_meta_groups(
    connection: sqlite3.Connection,
) -> ASM.MetaGroupsDataset:
    """Retrieve all meta groups from the database."""
    ...


@log_timing(logger=logger, level=_timing_log_level)
def get_types(
    connection: sqlite3.Connection, only_published: bool = True
) -> ASM.TypesDataset:
    """Retrieve all types from the database."""
    ...
