"""Verify exhaustive compact PI choices without materializing every combination."""

from dataclasses import replace
from decimal import Decimal
from itertools import islice
from typing import Literal

import pytest

from pfmsoft.eve_argus.pi.catalog import load_catalog
from pfmsoft.eve_argus.pi.models import (
    CostBoundary,
    MarketPriceBasis,
    SourcePrice,
    Tier,
)
from pfmsoft.eve_argus.pi.scenarios import (
    best_scenario,
    build_scenario_graph,
    iter_scenarios,
    scenario_counts,
)

D = Decimal
SELL = MarketPriceBasis.JITA_SELL
RATE = D("0.1")


def market_prices() -> dict[int, SourcePrice]:
    """Provide one explicit synthetic market basis across all canonical materials."""
    return {
        type_id: SourcePrice(
            source_id=f"quote:{type_id}",
            label="Synthetic Jita sell 5%",
            type_id=type_id,
            unit_cost=D(10000),
            boundary=CostBoundary.OFF_PLANET,
            market_basis=SELL,
        )
        for type_id in load_catalog()
    }


def test_p1_choices_include_market_mining_and_p0_refining() -> None:
    """Root outputs are off-planet, while inputs preserve both production routes."""
    graph = build_scenario_graph(
        catalog=load_catalog(),
        product_type_ids=(2393,),
        market_prices=market_prices(),
        market_basis=SELL,
        tax_rate=RATE,
    )
    counts = scenario_counts(graph=graph, product_type_id=2393, manufacture=False)
    scenarios = tuple(
        iter_scenarios(graph=graph, product_type_id=2393, manufacture=False)
    )

    assert counts.total == counts.complete == len(scenarios) == 4
    assert len({scenario.scenario_id for scenario in scenarios}) == 4
    assert {node.material.type_id for node in graph.materials} == {2073, 2393}
    assert all(
        scenario.source.boundary == CostBoundary.OFF_PLANET for scenario in scenarios
    )
    made = [scenario for scenario in scenarios if scenario.stage is not None]
    assert len(made) == 2
    assert any(
        scenario.inputs[0].source.label == "Freely mined P0" for scenario in made
    )
    assert (
        scenario_counts(graph=graph, product_type_id=2393, manufacture=True).total == 2
    )


def test_p2_counts_match_lazy_expansion_and_preserve_expensive_choices() -> None:
    """Two P1 ingredients each have six local/exported source alternatives."""
    graph = build_scenario_graph(
        catalog=load_catalog(),
        product_type_ids=(2329,),
        market_prices=market_prices(),
        market_basis=SELL,
        tax_rate=RATE,
    )
    counts = scenario_counts(graph=graph, product_type_id=2329, manufacture=True)
    scenarios = tuple(
        iter_scenarios(graph=graph, product_type_id=2329, manufacture=True)
    )

    assert counts.total == counts.complete == len(scenarios) == 36
    assert len({scenario.scenario_id for scenario in scenarios}) == 36
    assert any(
        child.source.boundary == CostBoundary.ON_PLANET
        for scenario in scenarios
        for child in scenario.inputs
    )
    assert any(
        child.stage is not None and child.source.boundary == CostBoundary.OFF_PLANET
        for scenario in scenarios
        for child in scenario.inputs
    )
    costs = [scenario.source.unit_cost for scenario in scenarios]
    assert len(set(costs)) > 1
    best = best_scenario(graph=graph, product_type_id=2329, manufacture=True)
    assert best is not None
    assert best.source.unit_cost == min(cost for cost in costs if cost is not None)
    assert best.scenario_id in {scenario.scenario_id for scenario in scenarios}


@pytest.mark.parametrize(
    ("electronics_price", "buy_electronics", "total_cost"),
    [("100", True, 27400), ("200", False, 27600)],
)
def test_best_p3_compares_delivered_cost_not_just_source_price(
    electronics_price: str, buy_electronics: bool, total_cost: int
) -> None:
    """Import taxes can make an integrated P2 cheaper than its lower market quote."""
    catalog = load_catalog()
    prices = market_prices()
    for type_id in (2398, 2399, 2400, 2401):
        prices[type_id] = replace(prices[type_id], unit_cost=D(10))
    prices[9836] = replace(prices[9836], unit_cost=D(electronics_price))
    graph = build_scenario_graph(
        catalog=catalog,
        product_type_ids=(9848,),
        market_prices=prices,
        market_basis=SELL,
        tax_rate=RATE,
    )
    result = best_scenario(graph=graph, product_type_id=9848, manufacture=True)

    assert result is not None and result.stage is not None
    parts, electronics = result.inputs
    assert parts.stage is not None
    assert parts.source.unit_cost == 480
    assert parts.source.boundary == CostBoundary.ON_PLANET
    assert all(child.stage is None for child in parts.inputs)
    assert {child.source.unit_cost for child in parts.inputs} == {D(10)}
    if buy_electronics:
        assert electronics.stage is None
        assert electronics.source.unit_cost == 100
        assert electronics.source.boundary == CostBoundary.OFF_PLANET
    else:
        assert electronics.stage is not None
        assert electronics.source.unit_cost == 480
        assert electronics.source.boundary == CostBoundary.ON_PLANET
    assert result.stage.import_tax == (3600 if buy_electronics else 0)
    assert result.stage.export_tax == 18000
    assert result.source.unit_cost == D(total_cost) / 3


def test_finished_purchase_is_separate_from_forced_production() -> None:
    """The cheapest finished purchase cannot masquerade as a manufacturing strategy."""
    prices = market_prices()
    prices[9848] = replace(prices[9848], unit_cost=D(1))
    graph = build_scenario_graph(
        catalog=load_catalog(),
        product_type_ids=(9848,),
        market_prices=prices,
        market_basis=SELL,
        tax_rate=RATE,
    )
    overall = best_scenario(graph=graph, product_type_id=9848, manufacture=False)
    made = best_scenario(graph=graph, product_type_id=9848, manufacture=True)

    assert overall is not None and overall.stage is None
    assert overall.source.unit_cost == 1
    assert made is not None and made.stage is not None
    assert made.source.boundary == CostBoundary.OFF_PLANET


def test_unavailable_mining_source_remains_in_graph_and_counted_alternatives() -> None:
    """Unsupported mining choices remain visible but are excluded from complete counts."""
    graph = build_scenario_graph(
        catalog=load_catalog(),
        product_type_ids=(2327,),
        market_prices=market_prices(),
        market_basis=SELL,
        tax_rate=RATE,
    )
    counts = scenario_counts(graph=graph, product_type_id=2327, manufacture=False)
    root = next(node for node in graph.materials if node.material.type_id == 2327)

    assert counts.total == 38
    assert counts.complete == 37
    assert len(root.sources) == 2
    assert root.sources[1].source.unit_cost is None
    assert "single planet" in str(root.sources[1].source.unavailable_reason)
    assert (
        sum(
            scenario.source.unit_cost is not None
            for scenario in iter_scenarios(
                graph=graph, product_type_id=2327, manufacture=False
            )
        )
        == counts.complete
    )
    assert (
        best_scenario(graph=graph, product_type_id=2327, manufacture=False) is not None
    )


def test_no_complete_route_returns_none_without_hiding_unknown_scenarios() -> None:
    """Absent market/mining references produce explicit unavailable leaf quotes."""
    catalog = load_catalog()
    unknown_planets = {
        2073: replace(catalog[2073], raw_planet_types=()),
        2393: catalog[2393],
    }
    graph = build_scenario_graph(
        catalog=unknown_planets,
        product_type_ids=(2393,),
        market_prices={},
        market_basis=SELL,
        tax_rate=RATE,
    )
    counts = scenario_counts(graph=graph, product_type_id=2393, manufacture=False)
    scenarios = tuple(
        iter_scenarios(graph=graph, product_type_id=2393, manufacture=False)
    )

    assert counts.total == len(scenarios) == 4
    assert counts.complete == 0
    assert best_scenario(graph=graph, product_type_id=2393, manufacture=True) is None
    assert all(scenario.source.unit_cost is None for scenario in scenarios)
    assert all(scenario.source.unavailable_reason for scenario in scenarios)
    assert any(
        "No supplied" in str(scenario.source.unavailable_reason)
        for scenario in scenarios
    )


def test_full_catalog_has_compact_shared_nodes_despite_large_p4_counts() -> None:
    """Store each dependency once and expand only requested concrete outcomes."""
    catalog = load_catalog()
    graph = build_scenario_graph(
        catalog=catalog,
        product_type_ids=tuple(catalog),
        market_prices=market_prices(),
        market_basis=SELL,
        tax_rate=RATE,
    )

    assert len(graph.materials) == 83
    assert len({node.material.type_id for node in graph.materials}) == 83
    assert (
        sum(len(node.sources) + len(node.production) for node in graph.materials) < 400
    )
    counts = scenario_counts(graph=graph, product_type_id=2876, manufacture=True)
    assert counts.total > 1_000_000_000
    first = tuple(
        islice(
            iter_scenarios(graph=graph, product_type_id=2876, manufacture=True),
            3,
        )
    )
    assert len(first) == 3
    assert len({scenario.scenario_id for scenario in first}) == 3
    assert (
        best_scenario(graph=graph, product_type_id=2876, manufacture=True) is not None
    )


@pytest.mark.parametrize(
    ("first_rate", "second_rate"),
    [("0.10", "0.1"), ("0.00", "-0"), ("1.0", "1")],
)
def test_ids_counts_and_ties_are_stable_across_input_order_and_equivalent_rates(
    first_rate: str, second_rate: str
) -> None:
    """Equivalent rate spellings and lookup insertion order do not alter choices."""
    catalog = load_catalog()
    prices = market_prices()
    first = build_scenario_graph(
        catalog=catalog,
        product_type_ids=(2393, 2396, 2393),
        market_prices=prices,
        market_basis=SELL,
        tax_rate=D(first_rate),
    )
    second = build_scenario_graph(
        catalog=dict(reversed(catalog.items())),
        product_type_ids=(2396, 2393),
        market_prices=dict(reversed(prices.items())),
        market_basis=SELL,
        tax_rate=D(second_rate),
    )

    assert first == second
    assert best_scenario(graph=first, product_type_id=2393, manufacture=True) == (
        best_scenario(graph=second, product_type_id=2393, manufacture=True)
    )
    assert tuple(
        iter_scenarios(graph=first, product_type_id=2393, manufacture=False)
    ) == tuple(iter_scenarios(graph=second, product_type_id=2393, manufacture=False))


@pytest.mark.parametrize("defect", ["basis", "identity", "boundary", "tax"])
def test_graph_rejects_incompatible_market_inputs(
    defect: Literal["basis", "identity", "boundary", "tax"],
) -> None:
    """Bad inputs fail rather than mixing assumptions or omitting import taxes."""
    prices = market_prices()
    quote = prices[2393]
    match defect:
        case "basis":
            quote = replace(quote, market_basis=MarketPriceBasis.JITA_BUY)
        case "identity":
            quote = replace(quote, type_id=2396)
        case "boundary":
            quote = replace(quote, boundary=CostBoundary.ON_PLANET)
        case "tax":
            quote = replace(quote, tax_rate=D("0.06"))
    prices[2393] = quote
    with pytest.raises(ValueError):
        build_scenario_graph(
            catalog=load_catalog(),
            product_type_ids=(2393,),
            market_prices=prices,
            market_basis=SELL,
            tax_rate=RATE,
        )


def test_invalid_catalog_and_product_scope_fail_before_recursing() -> None:
    """Catalog validation prevents cycles and invalid roots from entering the graph."""
    catalog = load_catalog()
    for roots in ((), (999999,)):
        with pytest.raises(ValueError):
            build_scenario_graph(
                catalog=catalog,
                product_type_ids=roots,
                market_prices={},
                market_basis=SELL,
                tax_rate=RATE,
            )
    malformed = dict(catalog)
    malformed[2073] = replace(
        catalog[2073],
        tier=Tier.P1,
        inputs=catalog[2393].inputs,
        raw_planet_types=(),
    )
    with pytest.raises(ValueError):
        build_scenario_graph(
            catalog=malformed,
            product_type_ids=(2393,),
            market_prices={},
            market_basis=SELL,
            tax_rate=RATE,
        )


def test_raw_material_has_no_manufacturing_scenario() -> None:
    """P0 can be acquired but not manufactured by an empty-input recipe."""
    graph = build_scenario_graph(
        catalog=load_catalog(),
        product_type_ids=(2073,),
        market_prices=market_prices(),
        market_basis=SELL,
        tax_rate=RATE,
    )
    counts = scenario_counts(graph=graph, product_type_id=2073, manufacture=True)
    assert counts.total == counts.complete == 0
    assert (
        tuple(iter_scenarios(graph=graph, product_type_id=2073, manufacture=True)) == ()
    )
    assert best_scenario(graph=graph, product_type_id=2073, manufacture=True) is None


def test_queries_reject_materials_outside_the_graph() -> None:
    """A missing graph node is a selection error, not an empty or free result."""
    graph = build_scenario_graph(
        catalog=load_catalog(),
        product_type_ids=(2393,),
        market_prices=market_prices(),
        market_basis=SELL,
        tax_rate=RATE,
    )
    with pytest.raises(ValueError, match="not represented"):
        scenario_counts(graph=graph, product_type_id=9848, manufacture=False)
    with pytest.raises(ValueError, match="not represented"):
        best_scenario(graph=graph, product_type_id=9848, manufacture=False)
    with pytest.raises(ValueError, match="not represented"):
        tuple(iter_scenarios(graph=graph, product_type_id=9848, manufacture=False))
