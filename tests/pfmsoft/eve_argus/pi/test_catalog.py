"""Verify PI recipe references and mining eligibility without live game data."""

from collections import Counter
from dataclasses import replace
from decimal import Decimal
from typing import Literal

import pytest

from pfmsoft.eve_argus.pi.catalog import (
    build_catalog,
    load_catalog,
    mining_planet_types,
)
from pfmsoft.eve_argus.pi.models import Material, PlanetType, RecipeInput, Tier


def test_catalog_covers_full_range_and_resolves_named_reference_aliases() -> None:
    """Canonical IDs resolve the spelling variants present in the Markdown."""
    catalog = load_catalog()

    assert Counter(material.tier for material in catalog.values()) == {
        Tier.P0: 15,
        Tier.P1: 15,
        Tier.P2: 24,
        Tier.P3: 21,
        Tier.P4: 8,
    }
    assert catalog[2393].inputs == (RecipeInput(type_id=2073, quantity=3000),)
    assert catalog[17136].inputs == (
        RecipeInput(type_id=3691, quantity=10),
        RecipeInput(type_id=9838, quantity=10),
    )
    assert catalog[2869].inputs == (
        RecipeInput(type_id=2360, quantity=6),
        RecipeInput(type_id=17136, quantity=6),
        RecipeInput(type_id=2398, quantity=40),
    )
    assert catalog[2875].inputs[0] == RecipeInput(type_id=3645, quantity=40)


def test_mining_eligibility_intersects_raw_resource_planets() -> None:
    """Eligibility is derived through recipes rather than assumed for every P2."""
    catalog = load_catalog()

    assert mining_planet_types(catalog=catalog, type_id=9832) == (
        PlanetType.GAS,
        PlanetType.STORM,
    )
    assert mining_planet_types(catalog=catalog, type_id=44) == (PlanetType.PLASMA,)
    assert mining_planet_types(catalog=catalog, type_id=2327) == ()
    assert mining_planet_types(catalog=catalog, type_id=2319) == (
        PlanetType.BARREN,
        PlanetType.ICE,
        PlanetType.OCEANIC,
        PlanetType.TEMPERATE,
    )


def test_unknown_material_is_an_explicit_lookup_error() -> None:
    """Bad references are not treated as unavailable mining opportunities."""
    with pytest.raises(ValueError, match="Unknown PI material 999"):
        mining_planet_types(catalog=load_catalog(), type_id=999)


@pytest.mark.parametrize("defect", ["duplicate", "missing", "cycle", "same-tier"])
def test_catalog_rejects_inconsistent_recipe_graphs(
    defect: Literal["duplicate", "missing", "cycle", "same-tier"],
) -> None:
    """Missing/duplicate references and non-descending dependencies fail validation."""
    catalog = load_catalog()
    materials = list(catalog.values())
    match defect:
        case "duplicate":
            materials.append(catalog[2393])
        case "missing":
            materials = [material for material in materials if material.type_id != 2073]
        case "cycle":
            materials = [
                replace(
                    material,
                    inputs=(
                        RecipeInput(
                            type_id=2329 if material.type_id == 2393 else 2393,
                            quantity=1,
                        ),
                    ),
                )
                if material.type_id in (2393, 2329)
                else material
                for material in materials
            ]
        case "same-tier":
            materials = [
                replace(
                    material,
                    inputs=(RecipeInput(type_id=2396, quantity=3000),),
                )
                if material.type_id == 2393
                else material
                for material in materials
            ]
    with pytest.raises(ValueError):
        build_catalog(materials)


def test_invalid_recipe_quantities_are_rejected() -> None:
    """A zero-size output cannot become a divisor in costing."""
    with pytest.raises(ValueError, match="output_quantity"):
        replace(load_catalog()[2393], output_quantity=0)
    with pytest.raises(ValueError, match="quantity"):
        RecipeInput(type_id=2073, quantity=-1)


def test_reference_data_cannot_supply_nonfinite_taxable_values() -> None:
    """Nonfinite reference values cannot contaminate an otherwise valid quote."""
    with pytest.raises(ValueError, match="taxable_base"):
        replace(load_catalog()[2393], taxable_base=Decimal("NaN"))


def test_duplicate_ingredients_are_rejected() -> None:
    """A recipe cannot charge the same ingredient twice under duplicate rows."""
    material = load_catalog()[2329]
    with pytest.raises(ValueError, match="Duplicate input"):
        replace(material, inputs=(material.inputs[0], material.inputs[0]))


def test_nonraw_materials_require_a_recipe() -> None:
    """Only extraction-tier materials can have no recipe inputs."""
    with pytest.raises(ValueError, match="recipe"):
        Material(
            type_id=1,
            name="Invalid refined material",
            tier=Tier.P1,
            volume=Decimal("0.19"),
            taxable_base=Decimal(400),
            output_quantity=20,
        )
