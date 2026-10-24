"""Helpers directly related to the static database."""

from pfmsoft.eve_argus.static.models import BlueprintRecord


def types_in_blueprint(blueprint: BlueprintRecord) -> set[int]:
    """Return the blueprint, material, and product type IDs, excluding skills.

    Includes all activities, ignoring missing activities and child collections.
    """
    types = {blueprint.blueprint_type_id}
    activities = blueprint.activities
    for activity in (
        activities.copying,
        activities.invention,
        activities.manufacturing,
        activities.reaction,
        activities.research_material,
        activities.research_time,
    ):
        if activity is None:
            continue
        types.update(material.type_id for material in activity.materials or ())
        types.update(product.type_id for product in activity.products or ())
    return types
