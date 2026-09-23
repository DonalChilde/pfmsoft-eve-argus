import json
import sqlite3
from dataclasses import asdict

from pfmsoft.eve_argus.helpers.package_resource import load_package_resouce_text
from pfmsoft.eve_argus.models.esd import esd_datasets as ESD
from pfmsoft.eve_argus.models.types import LanguageEnum

_table_def_parent = "pfmsoft.eve_argus.static.db"
_table_def_file = "table_definitions.sql"


def load_table_definitions() -> str:
    """Load the SQL table definitions for the market orders database."""
    return load_package_resouce_text(_table_def_parent, _table_def_file)


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


def write_blueprints(
    connection: sqlite3.Connection,
    blueprints: ESD.BlueprintsDataset,
) -> None:
    """Write the blueprints dataset to the database."""
    with connection:
        type_ids = {
            type_id for (type_id,) in connection.execute("SELECT type_id FROM types")
        }
        connection.executemany(
            """
            INSERT INTO blueprints (blueprint_type_id, max_production_limit)
            VALUES (?, ?)
            """,
            (
                (blueprint_type_id, record.maxProductionLimit)
                for blueprint_type_id, record in blueprints.dataset.items()
            ),
        )

        activity_rows = [
            (blueprint_type_id, activity_name, activity.time)
            for blueprint_type_id, record in blueprints.dataset.items()
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

        connection.executemany(
            """
            INSERT INTO blueprint_activity_materials (
                blueprint_type_id, activity, material_type_id, quantity
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                (blueprint_type_id, activity_name, material.typeID, material.quantity)
                for blueprint_type_id, record in blueprints.dataset.items()
                for activity_name in (
                    "copying",
                    "invention",
                    "manufacturing",
                    "reaction",
                    "research_material",
                    "research_time",
                )
                for activity in [getattr(record.activities, activity_name)]
                if activity is not None
                for material in activity.materials or []
                if material.typeID in type_ids
            ),
        )

        skill_rows = {
            (blueprint_type_id, activity_name, skill.typeID): (
                blueprint_type_id,
                activity_name,
                skill.typeID,
                skill.level,
            )
            for blueprint_type_id, record in blueprints.dataset.items()
            for activity_name in (
                "copying",
                "invention",
                "manufacturing",
                "reaction",
                "research_material",
                "research_time",
            )
            for activity in [getattr(record.activities, activity_name)]
            if activity is not None
            for skill in activity.skills or []
            if skill.typeID in type_ids
        }
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
            (
                (
                    blueprint_type_id,
                    activity_name,
                    product.typeID,
                    product.quantity,
                    product.probability,
                )
                for blueprint_type_id, record in blueprints.dataset.items()
                for activity_name in (
                    "copying",
                    "invention",
                    "manufacturing",
                    "reaction",
                    "research_material",
                    "research_time",
                )
                for activity in [getattr(record.activities, activity_name)]
                if activity is not None
                for product in activity.products or []
                if product.typeID in type_ids
            ),
        )
