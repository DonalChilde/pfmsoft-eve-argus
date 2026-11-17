"""Exercise source composition, explicit customs boundaries, and missing prices."""

from dataclasses import replace
from decimal import Decimal
from typing import Literal

import pytest

from pfmsoft.eve_argus.pi.catalog import load_catalog
from pfmsoft.eve_argus.pi.costing import calculate_stage, mined_source
from pfmsoft.eve_argus.pi.models import (
    CostBoundary,
    MarketPriceBasis,
    SourcePrice,
)

D = Decimal
SELL = MarketPriceBasis.JITA_SELL
RATE = D("0.1")


def market_source(type_id: int, price: str | None) -> SourcePrice:
    """Construct a synthetic sell-side reference or explicitly missing quote."""
    return SourcePrice(
        source_id=f"sell:{type_id}",
        label="Jita sell 5%",
        type_id=type_id,
        unit_cost=D(price) if price is not None else None,
        market_basis=SELL,
        boundary=CostBoundary.OFF_PLANET,
        unavailable_reason="No stored sell price" if price is None else None,
    )


@pytest.mark.parametrize(
    ("type_id", "expected"), [(2268, "0.4"), (2393, "40"), (9832, "720")]
)
def test_exported_mining_sources_charge_only_final_export(
    type_id: int, expected: str
) -> None:
    """Mined P0 and locally refined P1/P2 export at their own taxable bases."""
    source = mined_source(
        catalog=load_catalog(),
        type_id=type_id,
        tax_rate=RATE,
        export_output=True,
    )

    assert source.unit_cost == D(expected)
    assert source.market_basis is None
    assert source.boundary == CostBoundary.OFF_PLANET


def test_local_mined_source_is_free_but_not_exported() -> None:
    """Zero extraction cost is usable locally without first charging export."""
    source = mined_source(
        catalog=load_catalog(),
        type_id=2393,
        tax_rate=RATE,
        export_output=False,
    )
    assert source.unit_cost == 0
    assert source.boundary == CostBoundary.ON_PLANET


def test_unsupported_mined_p2_has_an_explicit_unavailable_reason() -> None:
    """A P2 with no common mining planet is not assigned the cheap mined price."""
    source = mined_source(
        catalog=load_catalog(),
        type_id=2327,
        tax_rate=RATE,
        export_output=True,
    )
    assert source.unit_cost is None
    assert source.unavailable_reason is not None
    assert "single planet" in source.unavailable_reason
    with pytest.raises(ValueError, match="P0, P1, or P2"):
        mined_source(
            catalog=load_catalog(),
            type_id=9848,
            tax_rate=RATE,
            export_output=True,
        )


def test_purchased_p0_refining_acceptance_example() -> None:
    """3000 P0 at 1 ISK plus 600 import and 800 export yields 220 ISK/P1."""
    result = calculate_stage(
        catalog=load_catalog(),
        product_type_id=2393,
        inputs=(market_source(2073, "1"),),
        tax_rate=RATE,
        market_basis=SELL,
        export_output=True,
        scenario_id="bacteria:from-p0",
    )
    assert result.acquisition_cost == 3000
    assert result.import_tax == 600
    assert result.export_tax == 800
    assert result.total_cost == 4400
    assert result.output.unit_cost == 220
    assert result.inputs[0].source.source_id == "sell:2073"


def test_workbook_p2_tax_formulas_with_synthetic_prices() -> None:
    """The workbook's valid 6% lower-tier customs components agree with the model."""
    result = calculate_stage(
        catalog=load_catalog(),
        product_type_id=2329,
        inputs=(market_source(2396, "100"), market_source(2399, "100")),
        tax_rate=D("0.06"),
        market_basis=SELL,
        export_output=True,
        scenario_id="biocells:6-percent",
    )
    assert result.import_tax == 960
    assert result.export_tax == 2160
    assert result.output.unit_cost == 2224


def test_staged_mixed_p3_retains_p2_export_and_adds_import_once() -> None:
    """One made P2 and one bought P2 compose using the P3's actual taxable base."""
    catalog = load_catalog()
    mechanical_parts = calculate_stage(
        catalog=catalog,
        product_type_id=3689,
        inputs=(market_source(2398, "100"), market_source(2399, "100")),
        tax_rate=RATE,
        market_basis=SELL,
        export_output=True,
        scenario_id="parts:from-p1",
    )
    assert mechanical_parts.output.unit_cost == 2640

    robotics = calculate_stage(
        catalog=catalog,
        product_type_id=9848,
        inputs=(mechanical_parts.output, market_source(9836, "1000")),
        tax_rate=RATE,
        market_basis=SELL,
        export_output=True,
        scenario_id="robotics:mixed",
    )
    assert robotics.inputs[0].source is mechanical_parts.output
    assert robotics.inputs[0].import_tax == 3600
    assert robotics.acquisition_cost == 36400
    assert robotics.import_tax == 7200
    assert robotics.export_tax == 18000
    assert robotics.total_cost == 61600
    assert robotics.output.unit_cost == D(61600) / 3


def test_integrated_intermediate_avoids_export_and_reimport() -> None:
    """Same-planet P2 costs retain their P1 imports, without P2 customs movements."""
    catalog = load_catalog()
    parts = calculate_stage(
        catalog=catalog,
        product_type_id=3689,
        inputs=(market_source(2398, "100"), market_source(2399, "100")),
        tax_rate=RATE,
        market_basis=SELL,
        export_output=False,
        scenario_id="parts:local",
    )
    assert parts.output.unit_cost == 1920
    assert parts.export_tax == 0
    result = calculate_stage(
        catalog=catalog,
        product_type_id=9848,
        inputs=(market_source(9836, "1000"), parts.output),
        tax_rate=RATE,
        market_basis=SELL,
        export_output=True,
        scenario_id="robotics:integrated",
    )
    assert result.import_tax == 3600
    assert result.total_cost == 50800
    assert result.inputs[0].source.type_id == 3689
    assert result.inputs[0].import_tax == 0


def test_p4_accepts_mined_and_purchased_sources() -> None:
    """A P4 direct P1 input can use the mined source beside purchased P3 inputs."""
    catalog = load_catalog()
    water = mined_source(
        catalog=catalog, type_id=3645, tax_rate=RATE, export_output=True
    )
    result = calculate_stage(
        catalog=catalog,
        product_type_id=2875,
        inputs=(water, market_source(2351, "100000"), market_source(28974, "100000")),
        tax_rate=RATE,
        market_basis=SELL,
        export_output=True,
        scenario_id="conduits:mixed",
    )
    assert result.acquisition_cost == 1201600
    assert result.import_tax == 36800
    assert result.export_tax == 120000
    assert result.output.unit_cost == 1358400


def test_missing_input_propagates_unknown_not_partial_total() -> None:
    """Known customs costs do not turn an incomplete material quote into a total."""
    result = calculate_stage(
        catalog=load_catalog(),
        product_type_id=2329,
        inputs=(market_source(2396, None), market_source(2399, "100")),
        tax_rate=RATE,
        market_basis=SELL,
        export_output=True,
        scenario_id="biocells:missing",
    )
    assert result.acquisition_cost is None
    assert result.total_cost is None
    assert result.output.unit_cost is None
    assert result.output.unavailable_reason is not None
    assert "sell:2396" in result.output.unavailable_reason
    assert "No stored sell price" in result.output.unavailable_reason
    assert result.import_tax == 1600
    assert result.export_tax == 3600


@pytest.mark.parametrize("defect", ["basis", "tax", "missing", "duplicate", "extra"])
def test_stage_rejects_inconsistent_sources(
    defect: Literal["basis", "tax", "missing", "duplicate", "extra"],
) -> None:
    """Scope errors are not silently reinterpreted as valid production alternatives."""
    first = market_source(2396, "100")
    inputs = (first, market_source(2399, "100"))
    match defect:
        case "basis":
            inputs = (replace(first, market_basis=MarketPriceBasis.JITA_BUY), inputs[1])
        case "tax":
            inputs = (replace(first, tax_rate=D("0.06")), inputs[1])
        case "missing":
            inputs = (first,)
        case "duplicate":
            inputs = (first, first)
        case "extra":
            inputs = (*inputs, market_source(2073, "1"))
    with pytest.raises(ValueError):
        calculate_stage(
            catalog=load_catalog(),
            product_type_id=2329,
            inputs=inputs,
            tax_rate=RATE,
            market_basis=SELL,
            export_output=True,
            scenario_id="invalid",
        )


@pytest.mark.parametrize("rate", ["-0.1", "1.01", "NaN", "Infinity"])
def test_invalid_tax_rates_raise(rate: str) -> None:
    """Only finite fractional rates from zero through one can be applied."""
    with pytest.raises(ValueError, match="tax_rate"):
        mined_source(
            catalog=load_catalog(),
            type_id=2393,
            tax_rate=D(rate),
            export_output=True,
        )


def test_zero_tax_and_zero_prices_are_valid_known_costs() -> None:
    """A genuinely zero price is distinct from an absent quote."""
    result = calculate_stage(
        catalog=load_catalog(),
        product_type_id=2393,
        inputs=(market_source(2073, "0"),),
        tax_rate=D(0),
        market_basis=SELL,
        export_output=True,
        scenario_id="zero",
    )
    assert result.output.unit_cost == 0
    assert result.output.unavailable_reason is None


def test_normalized_unit_cost_preserves_decimal_precision() -> None:
    """No float conversion or currency quantization occurs during source costing."""
    result = calculate_stage(
        catalog=load_catalog(),
        product_type_id=2393,
        inputs=(market_source(2073, "0.123456789123456789"),),
        tax_rate=D(0),
        market_basis=SELL,
        export_output=True,
        scenario_id="precise",
    )
    assert result.output.unit_cost == D("18.518518368518518350")


def test_missing_upstream_quote_remains_traceable_downstream() -> None:
    """An incomplete P2 cannot become a zero-cost input to a P3."""
    catalog = load_catalog()
    parts = calculate_stage(
        catalog=catalog,
        product_type_id=3689,
        inputs=(market_source(2398, None), market_source(2399, "100")),
        tax_rate=RATE,
        market_basis=SELL,
        export_output=True,
        scenario_id="missing-parts",
    )
    robotics = calculate_stage(
        catalog=catalog,
        product_type_id=9848,
        inputs=(parts.output, market_source(9836, "1000")),
        tax_rate=RATE,
        market_basis=SELL,
        export_output=True,
        scenario_id="missing-robotics",
    )
    assert robotics.total_cost is None
    assert robotics.output.unit_cost is None
    assert robotics.output.unavailable_reason is not None
    assert "missing-parts" in robotics.output.unavailable_reason
    assert "sell:2398" in robotics.output.unavailable_reason


def test_extraction_material_is_not_a_factory_recipe() -> None:
    """P0 extraction cannot be costed as a zero-input manufacturing stage."""
    with pytest.raises(ValueError, match="no production recipe"):
        calculate_stage(
            catalog=load_catalog(),
            product_type_id=2268,
            inputs=(),
            tax_rate=RATE,
            market_basis=SELL,
            export_output=True,
            scenario_id="invalid-p0",
        )


def test_nonfinite_prices_and_unexplained_missing_prices_raise() -> None:
    """An unavailable quote requires an explanation, while bad values fail fast."""
    source = market_source(2073, "1")
    for bad in (D("-1"), D("NaN"), D("Infinity")):
        with pytest.raises(ValueError, match="unit_cost"):
            replace(source, unit_cost=bad)
    with pytest.raises(ValueError, match="unavailable_reason"):
        replace(source, unit_cost=None)
