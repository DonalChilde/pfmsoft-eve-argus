"""Collect primary and component type IDs from fixed type-material records."""

from pfmsoft.eve_argus.static.models import TypeMaterialsDataset


def types_in_type_materials(type_materials: TypeMaterialsDataset) -> set[int]:
    """Return the set of types that appear in the type materials dataset.

    Includes parent types with empty material lists and all component materials.
    """
    return types_with_type_material(type_materials) | {
        material.material_type_id
        for record in type_materials.values()
        for material in record.materials
    }


def types_with_type_material(type_materials: TypeMaterialsDataset) -> set[int]:
    """Return the set of types that have a type material record in the dataset."""
    return set(type_materials)
