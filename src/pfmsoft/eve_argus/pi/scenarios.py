"""Compact exhaustive PI choices, lazy resolution, and best-complete costing.

Both same-planet and exported intermediate production are represented. Mining
sources always arrive at the agreed off-planet boundary; the graph does not infer
that mining can share an arbitrary factory planet. All facilities are notional.
"""

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from math import prod

from pfmsoft.eve_argus.pi.catalog import build_catalog, get_material
from pfmsoft.eve_argus.pi.costing import calculate_stage, mined_source
from pfmsoft.eve_argus.pi.models import (
    CostBoundary,
    MarketPriceBasis,
    Material,
    MaterialAlternatives,
    ProductionAlternative,
    RecipeInput,
    Scenario,
    ScenarioCounts,
    ScenarioGraph,
    SourceAlternative,
    SourcePrice,
    Tier,
    tax_rate_key,
    validate_tax_rate,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class _CostedScenario:
    """One complete candidate ranked on its cost at the consuming boundary.

    Attributes:
        effective_unit_cost: ISK per unit, including the next import if applicable.
        scenario: The original resolved outcome, without changing its source quote.
    """

    effective_unit_cost: Decimal
    scenario: Scenario


def build_scenario_graph(
    *,
    catalog: Mapping[int, Material],
    product_type_ids: tuple[int, ...],
    market_prices: Mapping[int, SourcePrice],
    market_basis: MarketPriceBasis,
    tax_rate: Decimal,
) -> ScenarioGraph:
    """Build shared branches without costing or expanding Cartesian products.

    Missing supplied quotes become explicit unavailable market alternatives, not
    zero prices. Unsupported P2 mining alternatives remain visible but incomplete.
    Supplied market quotes must be off-planet, tax-independent, and uniformly
    priced on market_basis.

    Raises:
        ValueError: If the catalog, roots, quotes, or tax assumptions are invalid.
    """
    validate_tax_rate(tax_rate)
    validated = build_catalog(catalog.values())
    if any(key != material.type_id for key, material in catalog.items()):
        raise ValueError("Catalog keys must match PI material identities.")
    if not product_type_ids:
        raise ValueError("Select at least one PI product type ID.")
    if any(type(type_id) is not int or type_id <= 0 for type_id in product_type_ids):
        raise ValueError("Product type IDs must be positive integers.")
    roots = tuple(sorted(set(product_type_ids)))
    for type_id in roots:
        get_material(validated, type_id=type_id)
    for type_id, quote in market_prices.items():
        get_material(validated, type_id=type_id)
        if (
            quote.type_id != type_id
            or quote.market_basis != market_basis
            or quote.boundary != CostBoundary.OFF_PLANET
            or quote.tax_rate is not None
        ):
            raise ValueError(f"Incompatible market quote for PI material {type_id}.")

    prefix = f"{market_basis.value}:tax-{tax_rate_key(tax_rate)}"
    nodes: dict[int, MaterialAlternatives] = {}

    def collect(type_id: int) -> MaterialAlternatives:
        """Memoize each material's choices and multiply exact dependency counts."""
        existing = nodes.get(type_id)
        if existing is not None:
            return existing
        material = validated[type_id]
        quote = market_prices.get(type_id)
        if quote is None:
            quote = SourcePrice(
                source_id=f"{prefix}:missing-market:{type_id}",
                label=market_basis.value,
                type_id=type_id,
                unit_cost=None,
                boundary=CostBoundary.OFF_PLANET,
                market_basis=market_basis,
                unavailable_reason=(
                    f"No supplied {market_basis.value} market price for "
                    f"{material.name} ({type_id})."
                ),
            )
        sources = [
            SourceAlternative(option_id=f"{prefix}:market:{type_id}", source=quote)
        ]
        if material.tier <= Tier.P2:
            sources.append(
                SourceAlternative(
                    option_id=f"{prefix}:mined:{type_id}",
                    source=mined_source(
                        catalog=validated,
                        type_id=type_id,
                        tax_rate=tax_rate,
                        export_output=True,
                    ),
                )
            )
        production: list[ProductionAlternative] = []
        if material.inputs:
            children = tuple(collect(item.type_id) for item in material.inputs)
            counts = ScenarioCounts(
                total=prod(child.counts.total for child in children),
                complete=prod(child.counts.complete for child in children),
            )
            for boundary in (CostBoundary.ON_PLANET, CostBoundary.OFF_PLANET):
                production.append(
                    ProductionAlternative(
                        option_id=f"{prefix}:make:{type_id}:{boundary.value}",
                        product_type_id=type_id,
                        boundary=boundary,
                        inputs=material.inputs,
                        counts=counts,
                    )
                )
        node = MaterialAlternatives(
            material=material,
            sources=tuple(sources),
            production=tuple(production),
            counts=ScenarioCounts(
                total=len(sources) + sum(branch.counts.total for branch in production),
                complete=sum(source.source.unit_cost is not None for source in sources)
                + sum(branch.counts.complete for branch in production),
            ),
        )
        nodes[type_id] = node
        return node

    for type_id in roots:
        collect(type_id)
    return ScenarioGraph(
        market_basis=market_basis,
        tax_rate=tax_rate,
        product_type_ids=roots,
        materials=tuple(nodes[type_id] for type_id in sorted(nodes)),
    )


def _material_node(
    nodes: Mapping[int, MaterialAlternatives], *, type_id: int
) -> MaterialAlternatives:
    """Resolve a graph material without disguising an invalid selection."""
    node = nodes.get(type_id)
    if node is None:
        raise ValueError(f"PI material {type_id} is not represented in this graph.")
    return node


def scenario_counts(
    *, graph: ScenarioGraph, product_type_id: int, manufacture: bool
) -> ScenarioCounts:
    """Count off-planet root outcomes, optionally requiring root manufacture.

    Child branches still include local and exported intermediate production.
    Counts include all source choices, even those unavailable or unprofitable.
    """
    nodes = {node.material.type_id: node for node in graph.materials}
    root = _material_node(nodes, type_id=product_type_id)
    branches = tuple(
        branch
        for branch in root.production
        if branch.boundary == CostBoundary.OFF_PLANET
    )
    return ScenarioCounts(
        total=(0 if manufacture else len(root.sources))
        + sum(branch.counts.total for branch in branches),
        complete=(
            0
            if manufacture
            else sum(source.source.unit_cost is not None for source in root.sources)
        )
        + sum(branch.counts.complete for branch in branches),
    )


def _source_scenario(option: SourceAlternative) -> Scenario:
    """Preserve a selected quote while identifying its place in the graph."""
    return Scenario(
        scenario_id=option.option_id,
        option_id=option.option_id,
        source=option.source,
    )


def _resolve_production(
    *,
    graph: ScenarioGraph,
    catalog: Mapping[int, Material],
    branch: ProductionAlternative,
    inputs: tuple[Scenario, ...],
) -> Scenario:
    """Resolve exactly one child combination using the existing stage calculator."""
    digest = sha256(
        "\n".join(child.scenario_id for child in inputs).encode("utf-8")
    ).hexdigest()
    scenario_id = f"{branch.option_id}:{digest}"
    stage = calculate_stage(
        catalog=catalog,
        product_type_id=branch.product_type_id,
        inputs=tuple(child.source for child in inputs),
        tax_rate=graph.tax_rate,
        market_basis=graph.market_basis,
        export_output=branch.boundary == CostBoundary.OFF_PLANET,
        scenario_id=scenario_id,
    )
    return Scenario(
        scenario_id=scenario_id,
        option_id=branch.option_id,
        source=stage.output,
        stage=stage,
        inputs=inputs,
    )


def iter_scenarios(
    *, graph: ScenarioGraph, product_type_id: int, manufacture: bool
) -> Iterator[Scenario]:
    """Lazily resolve all off-planet root outcomes, without truncation or pruning.

    Input combinations are traversed depth-first in canonical recipe order.
    Unlike itertools.product over iterators, this does not materialize child
    outcome pools, which can contain billions of scenarios for P4 chains.
    """
    nodes = {node.material.type_id: node for node in graph.materials}
    catalog = {type_id: node.material for type_id, node in nodes.items()}
    _material_node(nodes, type_id=product_type_id)

    def expand_inputs(
        requirements: tuple[RecipeInput, ...],
    ) -> Iterator[tuple[Scenario, ...]]:
        """Traverse the input Cartesian product one concrete combination at a time."""
        if not requirements:
            yield ()
            return
        first, *rest = requirements
        for source in expand(first.type_id, root=False):
            for remaining in expand_inputs(tuple(rest)):
                yield (source, *remaining)

    def expand(type_id: int, *, root: bool) -> Iterator[Scenario]:
        """Expand reusable branches only when the caller requests their next outcome."""
        node = nodes[type_id]
        if not root or not manufacture:
            for source in node.sources:
                yield _source_scenario(source)
        for branch in node.production:
            if root and branch.boundary != CostBoundary.OFF_PLANET:
                continue
            for inputs in expand_inputs(branch.inputs):
                yield _resolve_production(
                    graph=graph, catalog=catalog, branch=branch, inputs=inputs
                )

    yield from expand(product_type_id, root=True)


def best_scenario(
    *, graph: ScenarioGraph, product_type_id: int, manufacture: bool
) -> Scenario | None:
    """Find a cheapest complete off-planet outcome without exhaustive expansion.

    Input choices minimize delivered unit cost, including their next import when
    applicable. Linear, capacity-unconstrained unit costing makes these independent
    choices composable. Each node is evaluated once per call; other graph
    alternatives remain intact. None explicitly means no complete eligible route.

    Equal-cost choices use deterministic scenario-ID tie-breaking at each node.
    """
    nodes = {node.material.type_id: node for node in graph.materials}
    catalog = {type_id: node.material for type_id, node in nodes.items()}
    _material_node(nodes, type_id=product_type_id)
    cache: dict[int, tuple[Scenario, ...]] = {}

    def candidates(type_id: int) -> tuple[Scenario, ...]:
        """Resolve only each leaf and each branch's best complete child combination."""
        existing = cache.get(type_id)
        if existing is not None:
            return existing
        node = nodes[type_id]
        results = [
            _source_scenario(source)
            for source in node.sources
            if source.source.unit_cost is not None
        ]
        children: list[Scenario] = []
        for item in node.material.inputs:
            material = catalog[item.type_id]
            best_child = _cheapest_complete(
                candidates(item.type_id),
                import_tax=material.taxable_base * graph.tax_rate / 2,
            )
            if best_child is None:
                break
            children.append(best_child)
        if node.production and len(children) == len(node.material.inputs):
            for branch in node.production:
                results.append(
                    _resolve_production(
                        graph=graph,
                        catalog=catalog,
                        branch=branch,
                        inputs=tuple(children),
                    )
                )
        cache[type_id] = tuple(results)
        return cache[type_id]

    return _cheapest_complete(
        (
            candidate
            for candidate in candidates(product_type_id)
            if candidate.source.boundary == CostBoundary.OFF_PLANET
            and (not manufacture or candidate.stage is not None)
        ),
        import_tax=Decimal(0),
    )


def _cheapest_complete(
    candidates: Iterable[Scenario], *, import_tax: Decimal
) -> Scenario | None:
    """Rank complete quotes at a boundary without hiding other graph alternatives."""
    ranked: list[_CostedScenario] = []
    for candidate in candidates:
        cost = candidate.source.unit_cost
        if cost is not None:
            ranked.append(
                _CostedScenario(
                    effective_unit_cost=cost
                    + (
                        import_tax
                        if candidate.source.boundary == CostBoundary.OFF_PLANET
                        else Decimal(0)
                    ),
                    scenario=candidate,
                )
            )
    if not ranked:
        return None
    return min(
        ranked,
        key=lambda candidate: (
            candidate.effective_unit_cost,
            candidate.scenario.scenario_id,
        ),
    ).scenario
