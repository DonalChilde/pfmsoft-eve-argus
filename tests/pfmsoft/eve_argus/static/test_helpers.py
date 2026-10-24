"""Tests for static dataset helpers."""

import pytest

from pfmsoft.eve_argus.static import models as ASM
from pfmsoft.eve_argus.static.helpers import types_in_blueprint


def test_types_in_blueprint_without_activities() -> None:
    """Include the blueprint itself even when it has no activities."""
    blueprint = ASM.BlueprintRecord(
        blueprint_type_id=100,
        activities=ASM.BlueprintActivities(),
    )

    assert types_in_blueprint(blueprint) == {100}


@pytest.mark.parametrize(
    "activity_name",
    (
        "copying",
        "invention",
        "manufacturing",
        "reaction",
        "research_material",
        "research_time",
    ),
)
def test_types_in_blueprint_includes_each_activity(activity_name: str) -> None:
    """Every activity contributes materials and products, but not skills."""
    activities = ASM.BlueprintActivities()
    setattr(
        activities,
        activity_name,
        ASM.Blueprint_Activity(
            time=60,
            materials=(ASM.Blueprint_Material(type_id=1, quantity=10),),
            skills=(ASM.Blueprint_Skill(type_id=2, level=3),),
            products=(ASM.Blueprint_Product(type_id=3, quantity=4),),
        ),
    )
    blueprint = ASM.BlueprintRecord(
        blueprint_type_id=100,
        activities=activities,
    )

    assert types_in_blueprint(blueprint) == {100, 1, 3}


def test_types_in_blueprint_handles_empty_and_null_collections() -> None:
    """Present activities may have empty tuples or None for child collections."""
    blueprint = ASM.BlueprintRecord(
        blueprint_type_id=100,
        activities=ASM.BlueprintActivities(
            copying=ASM.Blueprint_Activity(time=0),
            research_time=ASM.Blueprint_Activity(
                time=0, materials=None, skills=None, products=None
            ),
        ),
    )

    assert types_in_blueprint(blueprint) == {100}


def test_types_in_blueprint_deduplicates_across_activities_and_roles() -> None:
    """Repeated IDs appear once, including references to the blueprint itself."""
    blueprint = ASM.BlueprintRecord(
        blueprint_type_id=100,
        activities=ASM.BlueprintActivities(
            manufacturing=ASM.Blueprint_Activity(
                time=60,
                materials=(ASM.Blueprint_Material(type_id=1, quantity=10),),
                skills=(ASM.Blueprint_Skill(type_id=1, level=3),),
                products=(ASM.Blueprint_Product(type_id=100, quantity=1),),
            ),
            invention=ASM.Blueprint_Activity(
                time=30,
                materials=(ASM.Blueprint_Material(type_id=1, quantity=5),),
                products=(ASM.Blueprint_Product(type_id=2, quantity=1),),
            ),
        ),
    )

    assert types_in_blueprint(blueprint) == {100, 1, 2}
