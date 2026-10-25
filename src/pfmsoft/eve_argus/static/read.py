"""Read datasets directly from the Argus static database."""

import json
import logging
import sqlite3
from typing import Any

from pfmsoft.eve_argus.helpers.sqlite_bool import int_to_bool
from pfmsoft.eve_argus.helpers.timing import log_timing
from pfmsoft.eve_argus.static import models as ASM

logger = logging.getLogger(__name__)
_timing_log_level = logging.INFO


@log_timing(logger=logger, level=_timing_log_level)
def blueprints(connection: sqlite3.Connection) -> ASM.BlueprintDataset:
    """Retrieve all blueprints with their activities and child records.

    Missing activities are None; present activities have tuples of materials,
    skills, and products, ordered by type ID. Blueprints are ordered by type ID.
    """
    rows = connection.execute(
        """
        SELECT blueprint_type_id, max_production_limit
        FROM blueprints
        ORDER BY blueprint_type_id
        """
    ).fetchall()

    materials: dict[tuple[int, str], list[ASM.Blueprint_Material]] = {}
    for blueprint_type_id, activity, type_id, quantity in connection.execute(
        """
        SELECT blueprint_type_id, activity, material_type_id, quantity
        FROM blueprint_activity_materials
        ORDER BY blueprint_type_id, activity, material_type_id
        """
    ):
        materials.setdefault((blueprint_type_id, activity), []).append(
            ASM.Blueprint_Material(type_id=type_id, quantity=quantity)
        )

    skills: dict[tuple[int, str], list[ASM.Blueprint_Skill]] = {}
    for blueprint_type_id, activity, type_id, level in connection.execute(
        """
        SELECT blueprint_type_id, activity, skill_type_id, level
        FROM blueprint_activity_skills
        ORDER BY blueprint_type_id, activity, skill_type_id
        """
    ):
        skills.setdefault((blueprint_type_id, activity), []).append(
            ASM.Blueprint_Skill(type_id=type_id, level=level)
        )

    products: dict[tuple[int, str], list[ASM.Blueprint_Product]] = {}
    for (
        blueprint_type_id,
        activity,
        type_id,
        quantity,
        probability,
    ) in connection.execute(
        """
        SELECT blueprint_type_id, activity, product_type_id, quantity, probability
        FROM blueprint_activity_products
        ORDER BY blueprint_type_id, activity, product_type_id
        """
    ):
        products.setdefault((blueprint_type_id, activity), []).append(
            ASM.Blueprint_Product(
                type_id=type_id, quantity=quantity, probability=probability
            )
        )

    result = {
        blueprint_type_id: ASM.BlueprintRecord(
            blueprint_type_id=blueprint_type_id,
            max_production_limit=max_production_limit,
            activities=ASM.BlueprintActivities(),
        )
        for blueprint_type_id, max_production_limit in rows
    }
    for blueprint_type_id, activity, time in connection.execute(
        """
        SELECT blueprint_type_id, activity, time
        FROM blueprint_activities
        ORDER BY blueprint_type_id, activity
        """
    ):
        key = (blueprint_type_id, activity)
        setattr(
            result[blueprint_type_id].activities,
            activity,
            ASM.Blueprint_Activity(
                time=time,
                materials=tuple(materials.get(key, ())),
                skills=tuple(skills.get(key, ())),
                products=tuple(products.get(key, ())),
            ),
        )

    logger.info("Retrieved %d blueprints", len(result))
    return result


@log_timing(logger=logger, level=_timing_log_level)
def market_groups(connection: sqlite3.Connection) -> ASM.MarketGroupsDataset:
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
            has_types=int_to_bool(has_types),
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
def industry_activities(
    connection: sqlite3.Connection,
) -> ASM.IndustryActivitiesDataset:
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
def map_regions(
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
def map_constellations(
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
def map_solar_systems(
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
            border=int_to_bool(border),
            constellation_id=constellation_id,
            corridor=int_to_bool(corridor),
            disallowed_anchor_categories=disallowed_categories.get(solar_system_id, ()),
            disallowed_anchor_groups=disallowed_groups.get(solar_system_id, ()),
            faction_id=faction_id,
            fringe=int_to_bool(fringe),
            hub=int_to_bool(hub),
            international=int_to_bool(international),
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
            regional=int_to_bool(regional),
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
def groups(
    connection: sqlite3.Connection, *, only_published: bool = True
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
            anchorable=int_to_bool(anchorable),
            anchored=int_to_bool(anchored),
            category_id=category_id,
            fittable_non_singleton=int_to_bool(fittable_non_singleton),
            icon_id=icon_id,
            name=name,
            published=int_to_bool(published),
            use_base_price=int_to_bool(use_base_price),
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
def categories(
    connection: sqlite3.Connection, *, only_published: bool = True
) -> ASM.CategoriesDataset:
    """Retrieve all categories from the database."""
    where_clause = "WHERE published = 1" if only_published else ""
    rows = connection.execute(
        f"""
        SELECT category_id, icon_id, name, published
        FROM categories
        {where_clause}
        ORDER BY category_id
        """
    ).fetchall()
    result = {
        category_id: ASM.CategoriesRecord(
            category_id=category_id,
            icon_id=icon_id,
            name=name,
            published=int_to_bool(published),
        )
        for category_id, icon_id, name, published in rows
    }
    logger.info("Retrieved %d categories", len(result))
    return result


@log_timing(logger=logger, level=_timing_log_level)
def type_materials(
    connection: sqlite3.Connection,
) -> ASM.TypeMaterialsDataset:
    """Retrieve all type materials from the database."""
    type_ids = connection.execute(
        """
        SELECT type_id
        FROM type_materials
        ORDER BY type_id
        """
    ).fetchall()
    materials_by_type_id: dict[int, list[ASM.Materials]] = {}
    for type_id, material_type_id, quantity in connection.execute(
        """
        SELECT type_id, material_type_id, quantity
        FROM type_material_components
        ORDER BY type_id, material_type_id
        """
    ):
        materials_by_type_id.setdefault(type_id, []).append(
            ASM.Materials(material_type_id=material_type_id, quantity=quantity)
        )

    result = {
        type_id: ASM.TypeMaterialsRecord(
            type_id=type_id,
            materials=tuple(materials_by_type_id.get(type_id, ())),
        )
        for (type_id,) in type_ids
    }
    logger.info("Retrieved %d type materials", len(result))
    return result


@log_timing(logger=logger, level=_timing_log_level)
def type_materials_randomized(
    connection: sqlite3.Connection,
) -> ASM.TypeMaterialsRandomizedDataset:
    """Retrieve all type materials from the database in randomized order."""
    type_ids = connection.execute(
        """
        SELECT type_id
        FROM type_materials_randomized
        ORDER BY type_id
        """
    ).fetchall()
    materials_by_type_id: dict[int, list[ASM.RandomizedMaterials]] = {}
    for type_id, material_type_id, quantity_min, quantity_max in connection.execute(
        """
        SELECT type_id, material_type_id, quantity_min, quantity_max
        FROM type_materials_randomized_components
        ORDER BY type_id, material_type_id
        """
    ):
        materials_by_type_id.setdefault(type_id, []).append(
            ASM.RandomizedMaterials(
                material_type_id=material_type_id,
                quantity_min=quantity_min,
                quantity_max=quantity_max,
            )
        )

    result = {
        type_id: ASM.TypeMaterialsRandomizedRecord(
            type_id=type_id,
            materials=tuple(materials_by_type_id.get(type_id, ())),
        )
        for (type_id,) in type_ids
    }
    logger.info("Retrieved %d randomized type material records", len(result))
    return result


@log_timing(logger=logger, level=_timing_log_level)
def meta_groups(
    connection: sqlite3.Connection,
) -> ASM.MetaGroupsDataset:
    """Retrieve all meta groups from the database."""
    rows = connection.execute(
        """
        SELECT meta_group_id, color, description, icon_id, icon_suffix, name
        FROM meta_groups
        ORDER BY meta_group_id
        """
    ).fetchall()

    def deserialize_color(value: str | None) -> ASM.Color | None:
        if value is None:
            return None
        color = json.loads(value)
        return ASM.Color(red=color["r"], green=color["g"], blue=color["b"])

    result = {
        meta_group_id: ASM.MetaGroupsRecord(
            meta_group_id=meta_group_id,
            color=deserialize_color(color),
            description=description,
            icon_id=icon_id,
            icon_suffix=icon_suffix,
            name=name,
        )
        for meta_group_id, color, description, icon_id, icon_suffix, name in rows
    }
    logger.info("Retrieved %d meta groups", len(result))
    return result


@log_timing(logger=logger, level=_timing_log_level)
def types(
    connection: sqlite3.Connection, *, only_published: bool = True
) -> ASM.TypesDataset:
    """Retrieve types with category IDs from their linked groups.

    Publication filtering applies only to types, not groups or categories.

    Raises:
        sqlite3.IntegrityError: If a selected type references a missing group.
    """
    where_clause = "WHERE t.published = 1" if only_published else ""
    rows = connection.execute(
        f"""
        SELECT
            t.type_id,
            t.base_price,
            t.capacity,
            t.description,
            t.faction_id,
            t.graphic_id,
            g.category_id,
            t.group_id,
            t.icon_id,
            t.is_dynamic_type,
            t.is_repackable,
            t.market_group_id,
            t.mass,
            t.meta_group_id,
            t.meta_level,
            t.name,
            t.packaged_volume,
            t.portion_size,
            t.published,
            t.race_id,
            t.radius,
            t.ship_tree_group_id,
            t.sound_id,
            t.tech_level,
            t.variation_parent_type_id,
            t.volume
        FROM types AS t
        LEFT JOIN groups AS g ON g.group_id = t.group_id
        {where_clause}
        ORDER BY t.type_id
        """
    ).fetchall()
    result: ASM.TypesDataset = {}
    for (
        type_id,
        base_price,
        capacity,
        description,
        faction_id,
        graphic_id,
        category_id,
        group_id,
        icon_id,
        is_dynamic_type,
        is_repackable,
        market_group_id,
        mass,
        meta_group_id,
        meta_level,
        name,
        packaged_volume,
        portion_size,
        published,
        race_id,
        radius,
        ship_tree_group_id,
        sound_id,
        tech_level,
        variation_parent_type_id,
        volume,
    ) in rows:
        if category_id is None:
            raise sqlite3.IntegrityError(
                f"Type references a missing group: type_id={type_id}, group_id={group_id}"
            )
        result[type_id] = ASM.TypesRecord(
            type_id=type_id,
            base_price=base_price,
            capacity=capacity,
            description=description,
            faction_id=faction_id,
            graphic_id=graphic_id,
            category_id=category_id,
            group_id=group_id,
            icon_id=icon_id,
            is_dynamic_type=int_to_bool(is_dynamic_type),
            is_repackable=int_to_bool(is_repackable),
            market_group_id=market_group_id,
            mass=mass,
            meta_group_id=meta_group_id,
            meta_level=meta_level,
            name=name,
            packaged_volume=packaged_volume,
            portion_size=portion_size,
            published=int_to_bool(published),
            race_id=race_id,
            radius=radius,
            ship_tree_group_id=ship_tree_group_id,
            sound_id=sound_id,
            tech_level=tech_level,
            variation_parent_type_id=variation_parent_type_id,
            volume=volume,
        )
    logger.info("Retrieved %d types", len(result))
    return result


@log_timing(logger=logger, level=_timing_log_level)
def sde_metadata(
    connection: sqlite3.Connection,
) -> ASM.SdeMetadata:
    """Retrieve the SDE metadata from the database."""
    row = connection.execute(
        """
        SELECT
            build_number,
            release_date
        FROM sde_metadata
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise ValueError("SDE metadata not found in the database.")
    build_number, release_date = row
    result = ASM.SdeMetadata(
        build_number=build_number,
        release_date=release_date,
    )
    logger.info("Retrieved SDE metadata: build_number=%d", result.build_number)
    return result


def metadata(connection: sqlite3.Connection) -> Any:
    """Retrieve the metadata from the Argus static db."""
    raise NotImplementedError("Metadata retrieval is not implemented yet.")
