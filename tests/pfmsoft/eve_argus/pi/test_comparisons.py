"""Verify spreadsheet-style source tiers without enumerating production outcomes."""

from dataclasses import replace
from decimal import Decimal

import pytest

from pfmsoft.eve_argus.pi.catalog import load_catalog
from pfmsoft.eve_argus.pi.comparisons import (
    build_grouped_comparisons,
    calculate_grouped_comparison,
    estimate_production,
)
from pfmsoft.eve_argus.pi.costing import calculate_stage
from pfmsoft.eve_argus.pi.models import (
    CostBoundary,
    MarketPriceBasis,
    SourcePrice,
    Tier,
)

D = Decimal
SELL = MarketPriceBasis.JITA_SELL
BUY = MarketPriceBasis.JITA_BUY
RATE = D("0.1")


def quote(
    type_id: int,
    price: str | None = "100",
    *,
    basis: MarketPriceBasis = SELL,
) -> SourcePrice:
    """Create an exact synthetic market input or sales valuation."""
    return SourcePrice(
        source_id=f"{basis.value}:{type_id}",
        label=basis.value,
        type_id=type_id,
        unit_cost=D(price) if price is not None else None,
        boundary=CostBoundary.OFF_PLANET,
        market_basis=basis,
        unavailable_reason="No price" if price is None else None,
    )


def test_all_workbook_groups_have_distinct_product_and_starting_tier_keys() -> None:
    """All seven E/F group pairs produce 105 comparison rows, not Cartesian rows."""
    catalog = load_catalog()
    result = build_grouped_comparisons(
        catalog=catalog,
        selected_sources={type_id: quote(type_id) for type_id in catalog},
        valuations={type_id: quote(type_id, basis=BUY) for type_id in catalog},
        market_basis=SELL,
        valuation_basis=BUY,
        tax_rate=RATE,
        intermediate_boundary=CostBoundary.ON_PLANET,
    )
    assert len(result) == 105
    assert len({row.comparison_id for row in result}) == 105
    assert {(row.starting_tier, row.product.tier) for row in result} == {
        (Tier.P0, Tier.P1),
        (Tier.P1, Tier.P2),
        (Tier.P1, Tier.P3),
        (Tier.P1, Tier.P4),
        (Tier.P2, Tier.P3),
        (Tier.P2, Tier.P4),
        (Tier.P3, Tier.P4),
    }
    assert sum(row.product.type_id == 2875 for row in result) == 3


@pytest.mark.parametrize(
    ("boundary", "expected"),
    [
        (CostBoundary.ON_PLANET, "56400"),
        (CostBoundary.OFF_PLANET, "78000"),
    ],
)
def test_p1_starting_robotics_expands_both_p2s(
    boundary: CostBoundary, expected: str
) -> None:
    """P1-to-P3 expands recipes; local intermediates avoid P2 customs movements."""
    catalog = load_catalog()
    result = calculate_grouped_comparison(
        catalog=catalog,
        product_type_id=9848,
        starting_tier=Tier.P1,
        selected_sources={type_id: quote(type_id) for type_id in catalog},
        valuation=quote(9848, "60000", basis=BUY),
        market_basis=SELL,
        valuation_basis=BUY,
        tax_rate=RATE,
        intermediate_boundary=boundary,
    )
    assert result.scenario.stage is not None
    assert result.scenario.stage.total_cost == D(expected)
    assert all(child.stage is not None for child in result.scenario.inputs)
    assert result.unit_profit == D("60000") - D(expected) / 3


def test_p2_starting_robotics_reuses_made_and_bought_p2_quotes() -> None:
    """A manufactured P2 is a starting quote, not a command to expand all P2s."""
    catalog = load_catalog()
    parts = calculate_stage(
        catalog=catalog,
        product_type_id=3689,
        inputs=(quote(2398), quote(2399)),
        tax_rate=RATE,
        market_basis=SELL,
        export_output=True,
        scenario_id="parts:from-p1",
    )
    result = calculate_grouped_comparison(
        catalog=catalog,
        product_type_id=9848,
        starting_tier=Tier.P2,
        selected_sources={3689: parts.output, 9836: quote(9836, "1000")},
        valuation=quote(9848, "30000", basis=BUY),
        market_basis=SELL,
        valuation_basis=BUY,
        tax_rate=RATE,
        intermediate_boundary=CostBoundary.ON_PLANET,
    )
    assert result.scenario.stage is not None
    assert result.scenario.stage.total_cost == 61600
    assert result.scenario.inputs[0].source is parts.output
    assert all(child.stage is None for child in result.scenario.inputs)
    assert result.unit_profit == D("30000") - D(61600) / 3


def test_p3_to_p4_retains_direct_p1_requirements() -> None:
    """Source-tier grouping does not discard lower-tier ingredients of a P4 recipe."""
    result = calculate_grouped_comparison(
        catalog=load_catalog(),
        product_type_id=2875,
        starting_tier=Tier.P3,
        selected_sources={
            3645: quote(3645, "40"),
            2351: quote(2351, "100000"),
            28974: quote(28974, "100000"),
        },
        valuation=quote(2875, "1500000", basis=BUY),
        market_basis=SELL,
        valuation_basis=BUY,
        tax_rate=RATE,
        intermediate_boundary=CostBoundary.ON_PLANET,
    )
    assert result.scenario.source.unit_cost == 1358400
    assert estimate_production(
        comparison=result, cycles_per_hour=D("0.5")
    ).units_per_hour == D("0.5")
    assert {child.source.type_id for child in result.scenario.inputs} == {
        3645,
        2351,
        28974,
    }


def test_missing_starting_quote_invalidates_only_dependent_costs() -> None:
    """Known taxes and an unrelated sales quote do not mask a missing ingredient."""
    result = calculate_grouped_comparison(
        catalog=load_catalog(),
        product_type_id=2329,
        starting_tier=Tier.P1,
        selected_sources={2396: quote(2396)},
        valuation=quote(2329, "3000", basis=BUY),
        market_basis=SELL,
        valuation_basis=BUY,
        tax_rate=RATE,
        intermediate_boundary=CostBoundary.ON_PLANET,
    )
    assert result.scenario.source.unit_cost is None
    assert result.scenario.source.unavailable_reason
    assert result.unit_profit is None
    assert (
        estimate_production(comparison=result, cycles_per_hour=D(0)).profit_per_hour
        is None
    )


def test_missing_sales_valuation_preserves_manufacturing_cost() -> None:
    """Missing sales data does not turn a known acquisition cost into missing data."""
    catalog = load_catalog()
    result = build_grouped_comparisons(
        catalog=catalog,
        selected_sources={type_id: quote(type_id) for type_id in catalog},
        valuations={},
        market_basis=SELL,
        valuation_basis=BUY,
        tax_rate=RATE,
        intermediate_boundary=CostBoundary.ON_PLANET,
    )
    assert all(row.scenario.source.unit_cost is not None for row in result)
    assert all(row.unit_profit is None for row in result)
    assert all(row.valuation.unavailable_reason for row in result)


@pytest.mark.parametrize(
    "source",
    [
        quote(2396, basis=BUY),
        replace(quote(2396), tax_rate=D("0.2")),
    ],
)
def test_shared_sources_must_match_acquisition_assumptions(source: SourcePrice) -> None:
    """Reused material prices cannot mix bases or customs rates."""
    with pytest.raises(ValueError, match="mismatch"):
        calculate_grouped_comparison(
            catalog=load_catalog(),
            product_type_id=2329,
            starting_tier=Tier.P1,
            selected_sources={2396: source, 2399: quote(2399)},
            valuation=quote(2329, "3000", basis=BUY),
            market_basis=SELL,
            valuation_basis=BUY,
            tax_rate=RATE,
            intermediate_boundary=CostBoundary.ON_PLANET,
        )


def test_cycles_per_hour_scale_profit_without_changing_unit_cost() -> None:
    """Twenty-four five-unit cycles/hour at ten ISK profit gives 1200 ISK/hour."""
    result = calculate_grouped_comparison(
        catalog=load_catalog(),
        product_type_id=2329,
        starting_tier=Tier.P1,
        selected_sources={2396: quote(2396), 2399: quote(2399)},
        valuation=quote(2329, "2650", basis=BUY),
        market_basis=SELL,
        valuation_basis=BUY,
        tax_rate=RATE,
        intermediate_boundary=CostBoundary.ON_PLANET,
    )
    estimate = estimate_production(comparison=result, cycles_per_hour=D(24))
    assert result.scenario.source.unit_cost == 2640
    assert estimate.units_per_hour == 120
    assert estimate.profit_per_hour == 1200
    assert estimate.profit_per_day == 28800
    assert estimate.profit_per_30_days == 864000
    half = estimate_production(comparison=result, cycles_per_hour=D("0.5"))
    assert half.units_per_hour == D("2.5")
    assert result.scenario.source.unit_cost == 2640
    with pytest.raises(ValueError, match="cycles_per_hour"):
        estimate_production(comparison=result, cycles_per_hour=D("-1"))


def test_grouped_comparison_rejects_a_local_shared_source() -> None:
    """Shared quotes cannot imply co-location with every consuming factory planet."""
    with pytest.raises(ValueError, match="off-planet"):
        calculate_grouped_comparison(
            catalog=load_catalog(),
            product_type_id=2329,
            starting_tier=Tier.P1,
            selected_sources={
                2396: replace(quote(2396), boundary=CostBoundary.ON_PLANET),
                2399: quote(2399),
            },
            valuation=quote(2329, "3000", basis=BUY),
            market_basis=SELL,
            valuation_basis=BUY,
            tax_rate=RATE,
            intermediate_boundary=CostBoundary.ON_PLANET,
        )
