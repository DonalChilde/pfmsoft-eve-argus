"""Pure normalized PI costs with explicit local/off-planet source boundaries."""

from collections.abc import Mapping
from decimal import Decimal

from pfmsoft.eve_argus.pi.catalog import get_material, mining_planet_types
from pfmsoft.eve_argus.pi.models import (
    CostBoundary,
    InputCost,
    MarketPriceBasis,
    Material,
    SourcePrice,
    StageCost,
    Tier,
    validate_tax_rate,
)


def mined_source(
    *,
    catalog: Mapping[int, Material],
    type_id: int,
    tax_rate: Decimal,
    export_output: bool,
) -> SourcePrice:
    """Quote free extraction/local refining, charging only the selected final export.

    Unsupported single-planet sources return an explicitly unavailable quote.
    Invalid identities, tiers, or rates raise ValueError instead.
    """
    validate_tax_rate(tax_rate)
    material = get_material(catalog, type_id=type_id)
    planets = mining_planet_types(catalog=catalog, type_id=type_id)
    boundary = CostBoundary.OFF_PLANET if export_output else CostBoundary.ON_PLANET
    label = (
        "Freely mined P0"
        if material.tier == Tier.P0
        else f"Freely mined with a {material.tier.name} result"
    )
    return SourcePrice(
        source_id=f"mined:{type_id}:{tax_rate}:{boundary.value}",
        label=label,
        type_id=type_id,
        unit_cost=(material.taxable_base * tax_rate if export_output else Decimal(0))
        if planets
        else None,
        boundary=boundary,
        tax_rate=tax_rate,
        unavailable_reason=None
        if planets
        else f"No single planet supplies the raw resources for {material.name}.",
    )


def calculate_stage(
    *,
    catalog: Mapping[int, Material],
    product_type_id: int,
    inputs: tuple[SourcePrice, ...],
    tax_rate: Decimal,
    market_basis: MarketPriceBasis,
    export_output: bool,
    scenario_id: str,
) -> StageCost:
    """Cost one recipe cycle and return a reusable unit quote without batch rounding.

    Input sources marked ON_PLANET are explicitly local to this stage. Other
    inputs incur import tax; upstream costs already in either source are never
    recalculated. All purchased leaves must share market_basis and all
    tax-dependent sources must share tax_rate.

    Missing source prices propagate to an unavailable output while leaving the
    known customs charges and original source references inspectable.

    Raises:
        ValueError: If the recipe, selected inputs, rate, or source assumptions
            are inconsistent.
    """
    validate_tax_rate(tax_rate)
    product = get_material(catalog, type_id=product_type_id)
    if not product.inputs:
        raise ValueError(f"PI material {product_type_id} has no production recipe.")
    sources = {source.type_id: source for source in inputs}
    if len(sources) != len(inputs):
        raise ValueError(f"Duplicate input sources for PI recipe {product_type_id}.")
    required = {item.type_id for item in product.inputs}
    if sources.keys() != required:
        raise ValueError(
            f"PI recipe {product_type_id} requires exactly input IDs "
            f"{sorted(required)}; received {sorted(sources)}."
        )

    input_costs: list[InputCost] = []
    missing: list[str] = []
    acquisition_cost = Decimal(0)
    import_tax = Decimal(0)
    for item in product.inputs:
        material = get_material(catalog, type_id=item.type_id)
        if material.tier >= product.tier:
            raise ValueError(
                f"Non-descending dependency for PI recipe {product_type_id}."
            )
        source = sources[item.type_id]
        if source.market_basis is not None and source.market_basis != market_basis:
            raise ValueError(
                f"Market-price basis mismatch for source {source.source_id}."
            )
        if source.tax_rate is not None and source.tax_rate != tax_rate:
            raise ValueError(
                f"Customs tax_rate mismatch for source {source.source_id}."
            )
        charge = (
            item.quantity * material.taxable_base * tax_rate / 2
            if source.boundary == CostBoundary.OFF_PLANET
            else Decimal(0)
        )
        cost = (
            item.quantity * source.unit_cost if source.unit_cost is not None else None
        )
        if cost is None:
            missing.append(f"{source.source_id}: {source.unavailable_reason}")
        else:
            acquisition_cost += cost
        import_tax += charge
        input_costs.append(
            InputCost(
                quantity=item.quantity,
                source=source,
                acquisition_cost=cost,
                import_tax=charge,
            )
        )
    export_tax = (
        product.output_quantity * product.taxable_base * tax_rate
        if export_output
        else Decimal(0)
    )
    total_cost = None if missing else acquisition_cost + import_tax + export_tax
    return StageCost(
        output_quantity=product.output_quantity,
        inputs=tuple(input_costs),
        acquisition_cost=None if missing else acquisition_cost,
        import_tax=import_tax,
        export_tax=export_tax,
        total_cost=total_cost,
        output=SourcePrice(
            source_id=scenario_id,
            label=f"{product.name} ({scenario_id})",
            type_id=product_type_id,
            unit_cost=total_cost / product.output_quantity
            if total_cost is not None
            else None,
            boundary=CostBoundary.OFF_PLANET
            if export_output
            else CostBoundary.ON_PLANET,
            market_basis=market_basis
            if any(source.market_basis is not None for source in inputs)
            else None,
            tax_rate=tax_rate,
            unavailable_reason="Unavailable input sources: " + "; ".join(missing)
            if missing
            else None,
        ),
    )
