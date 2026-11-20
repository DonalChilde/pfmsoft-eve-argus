"""Source-tier comparisons using shared off-planet quotes and explicit transfers."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from json import dumps

from pfmsoft.eve_argus.pi.catalog import build_catalog, get_material
from pfmsoft.eve_argus.pi.costing import calculate_stage
from pfmsoft.eve_argus.pi.models import (
    CostBoundary,
    MarketPriceBasis,
    Material,
    Scenario,
    SourcePrice,
    Tier,
    tax_rate_key,
    validate_tax_rate,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class GroupedComparison:
    """One product made from a starting tier, not a cheapest-route projection.

    Attributes:
        comparison_id: Stable route/configuration identity independent of sale value.
        product: Output material and its canonical per-cycle quantity.
        starting_tier: Tier at which recursive production consumes shared quotes;
            direct lower-tier recipe ingredients also consume shared quotes.
        intermediate_boundary: Whether expanded intermediates stay local or are
            exported and reimported. Shared starting quotes are always off-planet.
        scenario: Selected production tree with an exported root unit cost.
            Stage breakdowns retain their own cycle sizes; they are not additive
            route totals because upstream charges are embedded in source prices.
        valuation: Independently selected market sales quote, possibly unavailable.
        unit_profit: Sales valuation minus exported unit cost in ISK, or None if
            either is unknown. Excludes sales tax and transport fees.
    """

    comparison_id: str
    product: Material
    starting_tier: Tier
    intermediate_boundary: CostBoundary
    scenario: Scenario
    valuation: SourcePrice
    unit_profit: Decimal | None


@dataclass(slots=True, kw_only=True, frozen=True)
class ProductionEstimate:
    """Continuous-operation estimates, not factory-layout or market-fill guarantees.

    Attributes:
        cycles_per_hour: User-entered completed root recipe cycles/hour.
        units_per_hour: Root output quantity multiplied by completed cycles/hour.
        profit_per_hour: Unit profit multiplied by units/hour, or None if unknown.
        profit_per_day: Hourly profit times 24, or None if unknown.
        profit_per_30_days: Daily profit times 30, or None if unknown.
    """

    cycles_per_hour: Decimal
    units_per_hour: Decimal
    profit_per_hour: Decimal | None
    profit_per_day: Decimal | None
    profit_per_30_days: Decimal | None


def calculate_grouped_comparison(
    *,
    catalog: Mapping[int, Material],
    product_type_id: int,
    starting_tier: Tier,
    selected_sources: Mapping[int, SourcePrice],
    valuation: SourcePrice,
    market_basis: MarketPriceBasis,
    valuation_basis: MarketPriceBasis,
    tax_rate: Decimal,
    intermediate_boundary: CostBoundary,
) -> GroupedComparison:
    """Expand production above the starting tier, reusing selected quotes below it.

    A manufactured P2 selected as a starting quote retains its embedded costs and
    incurs import once; it is not expanded again. Expanded local intermediates
    incur neither export nor next-stage import. The output is always exported.

    Raises:
        ValueError: If tiers, catalog, quotes, or customs assumptions disagree.
    """
    validate_tax_rate(tax_rate)
    validated = build_catalog(catalog.values())
    if any(key != material.type_id for key, material in catalog.items()):
        raise ValueError("Catalog keys must match PI material identities.")
    product = get_material(validated, type_id=product_type_id)
    if type(starting_tier) is not Tier or not (
        starting_tier < product.tier
        and (starting_tier != Tier.P0 or product.tier == Tier.P1)
    ):
        raise ValueError("Invalid starting tier for this PI production group.")
    if type(intermediate_boundary) is not CostBoundary:
        raise ValueError("Invalid intermediate customs boundary.")
    for type_id, source in selected_sources.items():
        get_material(validated, type_id=type_id)
        if source.type_id != type_id:
            raise ValueError(f"Selected source identity disagrees for {type_id}.")
        if source.boundary != CostBoundary.OFF_PLANET:
            raise ValueError("Shared material sources must be off-planet quotes.")
        if source.market_basis is not None and source.market_basis != market_basis:
            raise ValueError(f"Market-price basis mismatch for {source.source_id}.")
        if source.tax_rate is not None and source.tax_rate != tax_rate:
            raise ValueError(f"Customs tax_rate mismatch for {source.source_id}.")
    if (
        valuation.type_id != product_type_id
        or valuation.market_basis != valuation_basis
        or valuation.tax_rate is not None
        or valuation.boundary != CostBoundary.OFF_PLANET
    ):
        raise ValueError("Incompatible output market valuation.")

    prefix = (
        f"group:{market_basis.value}:tax-{tax_rate_key(tax_rate)}:"
        f"from-{starting_tier.name}:intermediates-{intermediate_boundary.value}"
    )
    resolved: dict[int, Scenario] = {}

    def resolve(type_id: int) -> Scenario:
        """Resolve this route once per material without Cartesian expansion."""
        existing = resolved.get(type_id)
        if existing is not None:
            return existing
        material = validated[type_id]
        if material.tier <= starting_tier:
            source = selected_sources.get(type_id)
            if source is None:
                source = SourcePrice(
                    source_id=f"{prefix}:missing:{type_id}",
                    label="Missing selected source",
                    type_id=type_id,
                    unit_cost=None,
                    boundary=CostBoundary.OFF_PLANET,
                    market_basis=market_basis,
                    unavailable_reason=(
                        f"No selected starting source for {material.name} ({type_id})."
                    ),
                )
            scenario = Scenario(
                scenario_id=source.source_id,
                option_id=f"source:{source.source_id}",
                source=source,
            )
        else:
            children = tuple(resolve(item.type_id) for item in material.inputs)
            export = (
                type_id == product_type_id
                or intermediate_boundary == CostBoundary.OFF_PLANET
            )
            option_id = f"{prefix}:make:{type_id}:{'exported' if export else 'local'}"
            digest = sha256(
                dumps(tuple(child.scenario_id for child in children)).encode("utf-8")
            ).hexdigest()
            scenario_id = f"{option_id}:{digest}"
            stage = calculate_stage(
                catalog=validated,
                product_type_id=type_id,
                inputs=tuple(child.source for child in children),
                tax_rate=tax_rate,
                market_basis=market_basis,
                export_output=export,
                scenario_id=scenario_id,
            )
            scenario = Scenario(
                scenario_id=scenario_id,
                option_id=option_id,
                source=stage.output,
                stage=stage,
                inputs=children,
            )
        resolved[type_id] = scenario
        return scenario

    scenario = resolve(product_type_id)
    cost = scenario.source.unit_cost
    return GroupedComparison(
        comparison_id=f"{prefix}:product-{product_type_id}",
        product=product,
        starting_tier=starting_tier,
        intermediate_boundary=intermediate_boundary,
        scenario=scenario,
        valuation=valuation,
        unit_profit=valuation.unit_cost - cost
        if valuation.unit_cost is not None and cost is not None
        else None,
    )


def build_grouped_comparisons(
    *,
    catalog: Mapping[int, Material],
    selected_sources: Mapping[int, SourcePrice],
    valuations: Mapping[int, SourcePrice],
    market_basis: MarketPriceBasis,
    valuation_basis: MarketPriceBasis,
    tax_rate: Decimal,
    intermediate_boundary: CostBoundary,
) -> tuple[GroupedComparison, ...]:
    """Build the seven workbook tier groups in starting-tier/output-tier/ID order.

    Missing sale quotes retain available costs but cannot produce profit values.
    Local/exported variants are requested explicitly, not silently chosen.
    """
    comparisons: list[GroupedComparison] = []
    for starting_tier in (Tier.P0, Tier.P1, Tier.P2, Tier.P3):
        for product in sorted(
            catalog.values(), key=lambda material: (material.tier, material.type_id)
        ):
            if product.tier <= starting_tier or (
                starting_tier == Tier.P0 and product.tier != Tier.P1
            ):
                continue
            valuation = valuations.get(product.type_id)
            if valuation is None:
                valuation = SourcePrice(
                    source_id=f"missing-valuation:{valuation_basis.value}:{product.type_id}",
                    label=valuation_basis.value,
                    type_id=product.type_id,
                    unit_cost=None,
                    boundary=CostBoundary.OFF_PLANET,
                    market_basis=valuation_basis,
                    unavailable_reason=f"No output valuation for {product.name}.",
                )
            comparisons.append(
                calculate_grouped_comparison(
                    catalog=catalog,
                    product_type_id=product.type_id,
                    starting_tier=starting_tier,
                    selected_sources=selected_sources,
                    valuation=valuation,
                    market_basis=market_basis,
                    valuation_basis=valuation_basis,
                    tax_rate=tax_rate,
                    intermediate_boundary=intermediate_boundary,
                )
            )
    return tuple(comparisons)


def estimate_production(
    *, comparison: GroupedComparison, cycles_per_hour: Decimal
) -> ProductionEstimate:
    """Scale unit economics by completed cycles/hour, never by cycle duration."""
    if type(cycles_per_hour) is not Decimal:
        raise TypeError("cycles_per_hour must be a Decimal.")
    if not cycles_per_hour.is_finite() or cycles_per_hour < 0:
        raise ValueError("cycles_per_hour must be finite and nonnegative.")
    units = comparison.product.output_quantity * cycles_per_hour
    hourly = (
        comparison.unit_profit * units if comparison.unit_profit is not None else None
    )
    return ProductionEstimate(
        cycles_per_hour=cycles_per_hour,
        units_per_hour=units,
        profit_per_hour=hourly,
        profit_per_day=hourly * 24 if hourly is not None else None,
        profit_per_30_days=hourly * 24 * 30 if hourly is not None else None,
    )
