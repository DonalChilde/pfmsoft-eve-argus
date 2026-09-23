"""Query helpers for interacting with the EVE Argus static database."""

import json
import logging
import sqlite3
from dataclasses import asdict

from pfmsoft.eve_argus.helpers.package_resource import load_package_resouce_text
from pfmsoft.eve_argus.models.esd import esd_datasets as ESD
from pfmsoft.eve_argus.models.types import LanguageEnum

logger = logging.getLogger(__name__)

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


def _get_valid_blueprint_ids(
    connection: sqlite3.Connection,
    blueprints: ESD.BlueprintsDataset,
) -> set[int]:
    """Return blueprint IDs whose records satisfy the database constraints."""
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

        material_rows = []
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

        skill_rows = {}
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
                for skill in activity.skills or []:
                    skill_key = (blueprint_type_id, activity_name, skill.typeID)
                    skill_rows[skill_key] = (
                        blueprint_type_id,
                        activity_name,
                        skill.typeID,
                        skill.level,
                    )

        product_rows = []
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
