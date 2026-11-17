"""Verify offline assets, exact browser arithmetic, presets, and price exports."""

import json
import shutil
import subprocess
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import JsonValue, TypeAdapter
from whenever import Instant

from pfmsoft.eve_argus.dynamic.models import MarketOrdersResponse
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS
from pfmsoft.eve_argus.pi.catalog import load_catalog
from pfmsoft.eve_argus.pi.comparisons import (
    build_grouped_comparisons,
    calculate_grouped_comparison,
)
from pfmsoft.eve_argus.pi.costing import mined_source
from pfmsoft.eve_argus.pi.models import (
    CostBoundary,
    MarketPriceBasis,
    SourcePrice,
    Tier,
)
from pfmsoft.eve_argus.reports.pi_browser import PiMarketInputs, PiMaterialPrices
from pfmsoft.eve_argus.reports.pi_browser_render import render_pi_browser

D = Decimal
SELL = MarketPriceBasis.JITA_SELL
BUY = MarketPriceBasis.JITA_BUY


@pytest.fixture
def inputs() -> PiMarketInputs:
    """Provide exact synthetic prices for every material without external sources."""
    catalog = load_catalog()

    def quote(type_id: int, basis: MarketPriceBasis) -> SourcePrice:
        return SourcePrice(
            source_id=f"{basis.value}:{type_id}",
            label=basis.value,
            type_id=type_id,
            unit_cost=D("100.1234567890123456789"),
            market_basis=basis,
            boundary=CostBoundary.OFF_PLANET,
        )

    return PiMarketInputs(
        hub=next(hub for hub in MARKET_HUBS if hub.system_name == "Jita"),
        generated_at=Instant.parse_iso("2026-11-17T20:00:00Z"),
        response=MarketOrdersResponse(
            response_metadata_id=7,
            received_at="2026-11-17T19:00:00Z",
            expires_at=None,
            argus_expires_at=None,
            region_id=10000002,
        ),
        order_expires_at=None,
        order_freshness="unknown",
        history_window=None,
        materials=tuple(
            PiMaterialPrices(
                material=material,
                buy=quote(type_id, BUY),
                sell=quote(type_id, SELL),
                history=quote(type_id, MarketPriceBasis.HISTORY),
                history_metrics=None,
            )
            for type_id, material in catalog.items()
        ),
        warnings=("Order expiry unknown.",),
    )


def browser_result(
    tmp_path: Path, inputs: PiMarketInputs, expression: str
) -> JsonValue:
    """Run the actual packaged JavaScript with Node, not a Python reimplementation."""
    executable = shutil.which("node")
    if executable is None:
        pytest.skip("Node.js is required for browser calculation parity tests.")
    outputs = render_pi_browser(inputs)
    for name, content in outputs.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    html = outputs["index.html"]
    payload = json.loads(
        html.split('id="pi-data" type="application/json">', 1)[1].split("</script>", 1)[
            0
        ]
    )
    script = (
        "const fs = require('node:fs');"
        "const Decimal = require('./decimal.js');"
        "const factory = require('./engine.js');"
        "const payload = JSON.parse(fs.readFileSync(0, 'utf8'));"
        "const engine = factory(Decimal).create(payload);"
        "const state = engine.initialState();"
        f"console.log(JSON.stringify((() => {{ {expression} }})()));"
    )
    completed = subprocess.run(
        [executable, "-e", script],
        cwd=tmp_path,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return TypeAdapter[JsonValue](JsonValue).validate_json(completed.stdout)


def test_html_escapes_data_and_packages_every_offline_asset(
    inputs: PiMarketInputs,
) -> None:
    """Names cannot escape embedded JSON, and no external network assets are needed."""
    row = inputs.materials[0]
    dangerous = replace(row.material, name="</script><img src=x onerror=alert(1)>")
    rendered = render_pi_browser(
        replace(
            inputs, materials=(replace(row, material=dangerous), *inputs.materials[1:])
        )
    )
    assert set(rendered) == {
        "index.html",
        "engine.js",
        "app.js",
        "styles.css",
        "decimal.js",
        "decimal-LICENCE.txt",
    }
    html = rendered["index.html"]
    assert "</script><img" not in html
    assert "\\u003c/script\\u003e" in html
    assert 'src="decimal.js"' in html
    assert 'src="engine.js"' in html
    assert "https://" not in html
    assert "Permission is hereby granted" in rendered["decimal-LICENCE.txt"]


@pytest.mark.parametrize("boundary", list(CostBoundary))
@pytest.mark.parametrize("custom_sources", [False, True])
def test_browser_matches_python_for_every_group(
    inputs: PiMarketInputs, tmp_path: Path, boundary: CostBoundary, custom_sources: bool
) -> None:
    """Both intermediate-boundary modes match Python's Decimal cycle accounting."""
    overrides = (
        {"3645": "mined", "2393": "from-0", "3689": "from-1", "9848": "from-2"}
        if custom_sources
        else {}
    )
    actual = browser_result(
        tmp_path,
        inputs,
        f"state.intermediateBoundary = '{boundary.value}';"
        "state.valuationBasis = 'jita-buy-5';"
        f"state.choices = {json.dumps(overrides)};"
        "return engine.calculate(state).rows.map(r => [r.typeId, r.startingTier, r.cost]);",
    )
    sources = inputs.prices_for(SELL)
    if custom_sources:
        sources[3645] = mined_source(
            catalog=load_catalog(), type_id=3645, tax_rate=D("0.06"), export_output=True
        )
        for type_id, start in ((2393, 0), (3689, 1), (9848, 2)):
            sources[type_id] = calculate_grouped_comparison(
                catalog=load_catalog(),
                product_type_id=type_id,
                starting_tier=Tier(start),
                selected_sources=sources,
                valuation=inputs.prices_for(BUY)[type_id],
                market_basis=SELL,
                valuation_basis=BUY,
                tax_rate=D("0.06"),
                intermediate_boundary=boundary,
            ).scenario.source
    expected = build_grouped_comparisons(
        catalog=load_catalog(),
        selected_sources=sources,
        valuations=inputs.prices_for(BUY),
        market_basis=SELL,
        valuation_basis=BUY,
        tax_rate=D("0.06"),
        intermediate_boundary=boundary,
    )
    assert isinstance(actual, list)
    assert len(actual) == len(expected) == 105
    for received, row in zip(actual, expected, strict=True):
        assert isinstance(received, list)
        assert received[:2] == [row.product.type_id, int(row.starting_tier)]
        cost = received[2]
        assert isinstance(cost, str)
        assert D(cost) == row.scenario.source.unit_cost


def test_profitable_p2_preset_reuses_mixed_quotes_and_exports_only_selection(
    inputs: PiMarketInputs, tmp_path: Path
) -> None:
    """Profitable made P2 and purchased P2 feed downstream routes and partial export."""
    actual = browser_result(
        tmp_path,
        inputs,
        "engine.materials.get(3689).buy.unit_cost = '10000';"
        "engine.materials.get(9836).buy.unit_cost = '1';"
        "state.valuationBasis = 'jita-buy-5';"
        "state.preset = 'profitable-p2';"
        "const result = engine.calculate(state);"
        "return {parts: result.sources.get(3689).kind,"
        "electronics: result.sources.get(9836).kind,"
        "profile: engine.exportPrices(result, {'9848': 'from-2:9848'})};",
    )
    assert isinstance(actual, dict)
    assert actual["parts"] == "from-1"
    assert actual["electronics"] == "market"
    profile = actual["profile"]
    assert isinstance(profile, dict)
    prices = profile["prices"]
    assert isinstance(prices, dict)
    assert set(prices) == {"9848"}
    assert isinstance(prices["9848"], str)


def test_invalid_rate_and_unavailable_export_fail_explicitly(
    inputs: PiMarketInputs, tmp_path: Path
) -> None:
    """Invalid controls and missing selected costs cannot produce a partial export."""
    actual = browser_result(
        tmp_path,
        inputs,
        "const errors = [];"
        "state.taxRate = 'NaN';"
        "try { engine.calculate(state); } catch (e) { errors.push(e.message); }"
        "state.taxRate = '0.06';"
        "engine.materials.get(2396).sell.unit_cost = null;"
        "const result = engine.calculate(state);"
        "try { engine.exportPrices(result, {'2329': 'from-1:2329'}); }"
        "catch (e) { errors.push(e.message); }"
        "return errors;",
    )
    assert isinstance(actual, list)
    assert len(actual) == 2
    tax_error, export_error = actual
    assert isinstance(tax_error, str)
    assert isinstance(export_error, str)
    assert "tax" in tax_error.lower()
    assert "unavailable" in export_error.lower()
