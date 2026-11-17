"""Canonical P0-P4 recipes and raw-resource planets from markdown_docs/pi-stats.md.

IDs resolve reference aliases such as Micro Organisms/Microorganisms and Ukomi
Super Conductors/Ukomi Superconductors. This is a reviewed transcription of the
local reference, not a live SDE import or independent verification of game data.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from pfmsoft.eve_argus.pi.models import Material, PlanetType, RecipeInput, Tier


@dataclass(slots=True, kw_only=True, frozen=True)
class _TierProperties:
    """Reference properties shared by materials within one PI tier.

    Attributes:
        output_quantity: Whole output units per recipe cycle; one reference unit
            for P0, not an extraction-yield estimate.
        volume: Cubic meters per material unit.
        taxable_base: Customs valuation in ISK per unit, not a market price.
    """

    output_quantity: int
    volume: Decimal
    taxable_base: Decimal


@dataclass(slots=True, kw_only=True, frozen=True)
class _RecipeDefinition:
    """Canonical identity and ingredients, combined with tier properties on load.

    Attributes:
        type_id: Positive EVE inventory type ID of the output material.
        name: Human-readable canonical material name.
        tier: PI tier selecting shared output quantity, volume, and customs base.
        inputs: Per-cycle ingredient requirements; empty for P0 raw resources.
    """

    type_id: int
    name: str
    tier: Tier
    inputs: tuple[RecipeInput, ...] = ()


_TIER_DATA: dict[Tier, _TierProperties] = {
    Tier.P0: _TierProperties(
        output_quantity=1, volume=Decimal("0.005"), taxable_base=Decimal("4")
    ),
    Tier.P1: _TierProperties(
        output_quantity=20, volume=Decimal("0.19"), taxable_base=Decimal("400")
    ),
    Tier.P2: _TierProperties(
        output_quantity=5, volume=Decimal("0.75"), taxable_base=Decimal("7200")
    ),
    Tier.P3: _TierProperties(
        output_quantity=3, volume=Decimal("3"), taxable_base=Decimal("60000")
    ),
    Tier.P4: _TierProperties(
        output_quantity=1, volume=Decimal("50"), taxable_base=Decimal("1200000")
    ),
}

_RECIPES: tuple[_RecipeDefinition, ...] = (
    _RecipeDefinition(type_id=2268, name="Aqueous Liquids", tier=Tier.P0),
    _RecipeDefinition(type_id=2305, name="Autotrophs", tier=Tier.P0),
    _RecipeDefinition(type_id=2267, name="Base Metals", tier=Tier.P0),
    _RecipeDefinition(type_id=2288, name="Carbon Compounds", tier=Tier.P0),
    _RecipeDefinition(type_id=2287, name="Complex Organisms", tier=Tier.P0),
    _RecipeDefinition(type_id=2307, name="Felsic Magma", tier=Tier.P0),
    _RecipeDefinition(type_id=2272, name="Heavy Metals", tier=Tier.P0),
    _RecipeDefinition(type_id=2309, name="Ionic Solutions", tier=Tier.P0),
    _RecipeDefinition(type_id=2073, name="Microorganisms", tier=Tier.P0),
    _RecipeDefinition(type_id=2310, name="Noble Gas", tier=Tier.P0),
    _RecipeDefinition(type_id=2270, name="Noble Metals", tier=Tier.P0),
    _RecipeDefinition(type_id=2306, name="Non-CS Crystals", tier=Tier.P0),
    _RecipeDefinition(type_id=2286, name="Planktic Colonies", tier=Tier.P0),
    _RecipeDefinition(type_id=2311, name="Reactive Gas", tier=Tier.P0),
    _RecipeDefinition(type_id=2308, name="Suspended Plasma", tier=Tier.P0),
    _RecipeDefinition(
        type_id=2393,
        name="Bacteria",
        tier=Tier.P1,
        inputs=(RecipeInput(type_id=2073, quantity=3000),),
    ),
    _RecipeDefinition(
        type_id=2396,
        name="Biofuels",
        tier=Tier.P1,
        inputs=(RecipeInput(type_id=2288, quantity=3000),),
    ),
    _RecipeDefinition(
        type_id=3779,
        name="Biomass",
        tier=Tier.P1,
        inputs=(RecipeInput(type_id=2286, quantity=3000),),
    ),
    _RecipeDefinition(
        type_id=2401,
        name="Chiral Structures",
        tier=Tier.P1,
        inputs=(RecipeInput(type_id=2306, quantity=3000),),
    ),
    _RecipeDefinition(
        type_id=2390,
        name="Electrolytes",
        tier=Tier.P1,
        inputs=(RecipeInput(type_id=2309, quantity=3000),),
    ),
    _RecipeDefinition(
        type_id=2397,
        name="Industrial Fibers",
        tier=Tier.P1,
        inputs=(RecipeInput(type_id=2305, quantity=3000),),
    ),
    _RecipeDefinition(
        type_id=2392,
        name="Oxidizing Compound",
        tier=Tier.P1,
        inputs=(RecipeInput(type_id=2311, quantity=3000),),
    ),
    _RecipeDefinition(
        type_id=3683,
        name="Oxygen",
        tier=Tier.P1,
        inputs=(RecipeInput(type_id=2310, quantity=3000),),
    ),
    _RecipeDefinition(
        type_id=2389,
        name="Plasmoids",
        tier=Tier.P1,
        inputs=(RecipeInput(type_id=2308, quantity=3000),),
    ),
    _RecipeDefinition(
        type_id=2399,
        name="Precious Metals",
        tier=Tier.P1,
        inputs=(RecipeInput(type_id=2270, quantity=3000),),
    ),
    _RecipeDefinition(
        type_id=2395,
        name="Proteins",
        tier=Tier.P1,
        inputs=(RecipeInput(type_id=2287, quantity=3000),),
    ),
    _RecipeDefinition(
        type_id=2398,
        name="Reactive Metals",
        tier=Tier.P1,
        inputs=(RecipeInput(type_id=2267, quantity=3000),),
    ),
    _RecipeDefinition(
        type_id=9828,
        name="Silicon",
        tier=Tier.P1,
        inputs=(RecipeInput(type_id=2307, quantity=3000),),
    ),
    _RecipeDefinition(
        type_id=2400,
        name="Toxic Metals",
        tier=Tier.P1,
        inputs=(RecipeInput(type_id=2272, quantity=3000),),
    ),
    _RecipeDefinition(
        type_id=3645,
        name="Water",
        tier=Tier.P1,
        inputs=(RecipeInput(type_id=2268, quantity=3000),),
    ),
    _RecipeDefinition(
        type_id=2329,
        name="Biocells",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2396, quantity=40),
            RecipeInput(type_id=2399, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=3828,
        name="Construction Blocks",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2398, quantity=40),
            RecipeInput(type_id=2400, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=9836,
        name="Consumer Electronics",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2400, quantity=40),
            RecipeInput(type_id=2401, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=9832,
        name="Coolant",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2390, quantity=40),
            RecipeInput(type_id=3645, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=44,
        name="Enriched Uranium",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2399, quantity=40),
            RecipeInput(type_id=2400, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=3693,
        name="Fertilizer",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2393, quantity=40),
            RecipeInput(type_id=2395, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=15317,
        name="Genetically Enhanced Livestock",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2395, quantity=40),
            RecipeInput(type_id=3779, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=3725,
        name="Livestock",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2395, quantity=40),
            RecipeInput(type_id=2396, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=3689,
        name="Mechanical Parts",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2398, quantity=40),
            RecipeInput(type_id=2399, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=2327,
        name="Microfiber Shielding",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2397, quantity=40),
            RecipeInput(type_id=9828, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=9842,
        name="Miniature Electronics",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2401, quantity=40),
            RecipeInput(type_id=9828, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=2463,
        name="Nanites",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2393, quantity=40),
            RecipeInput(type_id=2398, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=2317,
        name="Oxides",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2392, quantity=40),
            RecipeInput(type_id=3683, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=2321,
        name="Polyaramids",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2392, quantity=40),
            RecipeInput(type_id=2397, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=3695,
        name="Polytextiles",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2396, quantity=40),
            RecipeInput(type_id=2397, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=9830,
        name="Rocket Fuel",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2389, quantity=40),
            RecipeInput(type_id=2390, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=3697,
        name="Silicate Glass",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2392, quantity=40),
            RecipeInput(type_id=9828, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=9838,
        name="Superconductors",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2389, quantity=40),
            RecipeInput(type_id=3645, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=2312,
        name="Supertensile Plastics",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=3683, quantity=40),
            RecipeInput(type_id=3779, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=3691,
        name="Synthetic Oil",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2390, quantity=40),
            RecipeInput(type_id=3683, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=2319,
        name="Test Cultures",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2393, quantity=40),
            RecipeInput(type_id=3645, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=9840,
        name="Transmitter",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2389, quantity=40),
            RecipeInput(type_id=2401, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=3775,
        name="Viral Agent",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2393, quantity=40),
            RecipeInput(type_id=3779, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=2328,
        name="Water-Cooled CPU",
        tier=Tier.P2,
        inputs=(
            RecipeInput(type_id=2398, quantity=40),
            RecipeInput(type_id=3645, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=2358,
        name="Biotech Research Reports",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=2463, quantity=10),
            RecipeInput(type_id=3725, quantity=10),
            RecipeInput(type_id=3828, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=2345,
        name="Camera Drones",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=9830, quantity=10),
            RecipeInput(type_id=3697, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=2344,
        name="Condensates",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=2317, quantity=10),
            RecipeInput(type_id=9832, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=2367,
        name="Cryoprotectant Solution",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=2319, quantity=10),
            RecipeInput(type_id=3691, quantity=10),
            RecipeInput(type_id=3693, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=17392,
        name="Data Chips",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=2312, quantity=10),
            RecipeInput(type_id=2327, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=2348,
        name="Gel-Matrix Biopaste",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=2317, quantity=10),
            RecipeInput(type_id=2329, quantity=10),
            RecipeInput(type_id=9838, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=9834,
        name="Guidance Systems",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=2328, quantity=10),
            RecipeInput(type_id=9840, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=2366,
        name="Hazmat Detection Systems",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=3695, quantity=10),
            RecipeInput(type_id=3775, quantity=10),
            RecipeInput(type_id=9840, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=2361,
        name="Hermetic Membranes",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=2321, quantity=10),
            RecipeInput(type_id=15317, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=17898,
        name="High-Tech Transmitters",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=2321, quantity=10),
            RecipeInput(type_id=9840, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=2360,
        name="Industrial Explosives",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=3693, quantity=10),
            RecipeInput(type_id=3695, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=2354,
        name="Neocoms",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=2329, quantity=10),
            RecipeInput(type_id=3697, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=2352,
        name="Nuclear Reactors",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=2327, quantity=10),
            RecipeInput(type_id=44, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=9846,
        name="Planetary Vehicles",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=2312, quantity=10),
            RecipeInput(type_id=3689, quantity=10),
            RecipeInput(type_id=9842, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=9848,
        name="Robotics",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=3689, quantity=10),
            RecipeInput(type_id=9836, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=2351,
        name="Smartfab Units",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=3828, quantity=10),
            RecipeInput(type_id=9842, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=2349,
        name="Supercomputers",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=2328, quantity=10),
            RecipeInput(type_id=9832, quantity=10),
            RecipeInput(type_id=9836, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=2346,
        name="Synthetic Synapses",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=2312, quantity=10),
            RecipeInput(type_id=2319, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=12836,
        name="Transcranial Microcontrollers",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=2329, quantity=10),
            RecipeInput(type_id=2463, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=17136,
        name="Ukomi Superconductors",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=3691, quantity=10),
            RecipeInput(type_id=9838, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=28974,
        name="Vaccines",
        tier=Tier.P3,
        inputs=(
            RecipeInput(type_id=3725, quantity=10),
            RecipeInput(type_id=3775, quantity=10),
        ),
    ),
    _RecipeDefinition(
        type_id=2867,
        name="Broadcast Node",
        tier=Tier.P4,
        inputs=(
            RecipeInput(type_id=2354, quantity=6),
            RecipeInput(type_id=17392, quantity=6),
            RecipeInput(type_id=17898, quantity=6),
        ),
    ),
    _RecipeDefinition(
        type_id=2868,
        name="Integrity Response Drones",
        tier=Tier.P4,
        inputs=(
            RecipeInput(type_id=2348, quantity=6),
            RecipeInput(type_id=2366, quantity=6),
            RecipeInput(type_id=9846, quantity=6),
        ),
    ),
    _RecipeDefinition(
        type_id=2869,
        name="Nano-Factory",
        tier=Tier.P4,
        inputs=(
            RecipeInput(type_id=2360, quantity=6),
            RecipeInput(type_id=17136, quantity=6),
            RecipeInput(type_id=2398, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=2870,
        name="Organic Mortar Applicators",
        tier=Tier.P4,
        inputs=(
            RecipeInput(type_id=2344, quantity=6),
            RecipeInput(type_id=9848, quantity=6),
            RecipeInput(type_id=2393, quantity=40),
        ),
    ),
    _RecipeDefinition(
        type_id=2871,
        name="Recursive Computing Module",
        tier=Tier.P4,
        inputs=(
            RecipeInput(type_id=2346, quantity=6),
            RecipeInput(type_id=9834, quantity=6),
            RecipeInput(type_id=12836, quantity=6),
        ),
    ),
    _RecipeDefinition(
        type_id=2872,
        name="Self-Harmonizing Power Core",
        tier=Tier.P4,
        inputs=(
            RecipeInput(type_id=2345, quantity=6),
            RecipeInput(type_id=2352, quantity=6),
            RecipeInput(type_id=2361, quantity=6),
        ),
    ),
    _RecipeDefinition(
        type_id=2875,
        name="Sterile Conduits",
        tier=Tier.P4,
        inputs=(
            RecipeInput(type_id=3645, quantity=40),
            RecipeInput(type_id=2351, quantity=6),
            RecipeInput(type_id=28974, quantity=6),
        ),
    ),
    _RecipeDefinition(
        type_id=2876,
        name="Wetware Mainframe",
        tier=Tier.P4,
        inputs=(
            RecipeInput(type_id=2349, quantity=6),
            RecipeInput(type_id=2358, quantity=6),
            RecipeInput(type_id=2367, quantity=6),
        ),
    ),
)

_RAW_PLANETS: dict[int, tuple[str, ...]] = {
    2268: ("Barren", "Gas", "Ice", "Oceanic", "Storm", "Temperate"),
    2305: ("Temperate",),
    2267: ("Barren", "Gas", "Lava", "Plasma", "Storm"),
    2288: ("Barren", "Oceanic", "Temperate"),
    2287: ("Oceanic", "Temperate"),
    2307: ("Lava",),
    2272: ("Ice", "Lava", "Plasma"),
    2309: ("Gas", "Storm"),
    2073: ("Barren", "Ice", "Oceanic", "Temperate"),
    2310: ("Gas", "Ice", "Storm"),
    2270: ("Barren", "Plasma"),
    2306: ("Lava", "Plasma"),
    2286: ("Ice", "Oceanic"),
    2311: ("Gas",),
    2308: ("Lava", "Plasma", "Storm"),
}


def build_catalog(materials: Iterable[Material]) -> dict[int, Material]:
    """Index and validate recipes, requiring every dependency to have a lower tier.

    Strictly descending tiers exclude cycles, including cycles across P4's
    direct P1 inputs, without depending on traversal order.

    Raises:
        ValueError: If IDs are duplicated, references are missing, or dependencies
            do not descend in tier.
    """
    catalog: dict[int, Material] = {}
    for material in materials:
        if material.type_id in catalog:
            raise ValueError(f"Duplicate PI material {material.type_id}.")
        catalog[material.type_id] = material
    for material in catalog.values():
        for item in material.inputs:
            dependency = get_material(catalog, type_id=item.type_id)
            if dependency.tier >= material.tier:
                raise ValueError(
                    f"PI recipe {material.type_id} input {item.type_id} must have "
                    "a lower tier; same-tier dependencies and cycles are invalid."
                )
    return dict(sorted(catalog.items()))


def load_catalog() -> dict[int, Material]:
    """Return a fresh validated catalog; never parse Markdown or access the network."""
    materials: list[Material] = []
    for recipe in _RECIPES:
        properties = _TIER_DATA[recipe.tier]
        materials.append(
            Material(
                type_id=recipe.type_id,
                name=recipe.name,
                tier=recipe.tier,
                volume=properties.volume,
                taxable_base=properties.taxable_base,
                output_quantity=properties.output_quantity,
                inputs=recipe.inputs,
                raw_planet_types=tuple(
                    PlanetType(planet)
                    for planet in _RAW_PLANETS.get(recipe.type_id, ())
                ),
            )
        )
    return build_catalog(materials)


def get_material(catalog: Mapping[int, Material], *, type_id: int) -> Material:
    """Resolve a known material without concealing invalid references."""
    material = catalog.get(type_id)
    if material is None:
        raise ValueError(f"Unknown PI material {type_id}.")
    if material.type_id != type_id:
        raise ValueError(f"Inconsistent PI material identity for {type_id}.")
    return material


def mining_planet_types(
    *, catalog: Mapping[int, Material], type_id: int
) -> tuple[PlanetType, ...]:
    """Find common raw-resource planets for P0/P1/P2 using validated recipe paths.

    This checks resource co-occurrence, not extractor output, layouts, or capacity.
    """
    material = get_material(catalog, type_id=type_id)
    if material.tier > Tier.P2:
        raise ValueError("Mining sources are supported only for P0, P1, or P2.")
    if material.tier == Tier.P0:
        return tuple(sorted(material.raw_planet_types))
    available = set(PlanetType)
    for item in material.inputs:
        dependency = get_material(catalog, type_id=item.type_id)
        if dependency.tier >= material.tier:
            raise ValueError(f"Non-descending mining dependency for {type_id}.")
        available.intersection_update(
            mining_planet_types(catalog=catalog, type_id=item.type_id)
        )
    return tuple(sorted(available))
