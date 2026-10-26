"""Tests for type-material membership helpers."""

from pfmsoft.eve_argus.helpers.type_materials import (
    types_in_type_materials,
    types_with_type_material,
)
from pfmsoft.eve_argus.static.models import Materials, TypeMaterialsRecord


def test_type_material_membership() -> None:
    """Include empty parents and deduplicate repeated component and parent IDs."""
    dataset = {
        10: TypeMaterialsRecord(
            type_id=10,
            materials=(
                Materials(material_type_id=20, quantity=5),
                Materials(material_type_id=30, quantity=1),
            ),
        ),
        20: TypeMaterialsRecord(
            type_id=20, materials=(Materials(material_type_id=30, quantity=2),)
        ),
        40: TypeMaterialsRecord(type_id=40, materials=()),
    }

    assert types_in_type_materials(dataset) == {10, 20, 30, 40}
    assert types_with_type_material(dataset) == {10, 20, 40}


def test_empty_type_material_membership() -> None:
    """Empty datasets have no primary or component types."""
    assert types_in_type_materials({}) == set()
    assert types_with_type_material({}) == set()
