"""Verify Jita-only PI source prices, history coverage, and snapshot provenance."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from whenever import Instant

from pfmsoft.eve_argus.dynamic.models import (
    BuySellOrders,
    MarketOrderRecord,
    MarketOrdersDataset,
    MarketOrdersResponse,
)
from pfmsoft.eve_argus.market_history.models import MarketHistoryRecord
from pfmsoft.eve_argus.models import market_hubs
from pfmsoft.eve_argus.pi.catalog import load_catalog
from pfmsoft.eve_argus.pi.models import MarketPriceBasis
from pfmsoft.eve_argus.reports.pi_browser import collect_pi_market_inputs
from pfmsoft.eve_argus.reports.station_trades import (
    RegionalHistory,
    select_history_window,
)

D = Decimal
GENERATED = Instant.parse_iso("2026-11-17T20:00:00Z")
RECEIVED = "2026-11-17T19:00:00Z"
JITA = next(hub for hub in market_hubs.MARKET_HUBS if hub.system_name == "Jita")
RESPONSE = MarketOrdersResponse(
    response_metadata_id=7,
    received_at=RECEIVED,
    expires_at="2026-11-17T19:05:00Z",
    argus_expires_at="2026-11-17T21:00:00Z",
    region_id=JITA.region_id,
)


def order(
    *,
    order_id: int,
    price: str,
    volume: int,
    buy: bool = False,
    station_id: int = JITA.station_id,
) -> MarketOrderRecord:
    """Make one synthetic P1 station order."""
    return MarketOrderRecord(
        response_metadata_id=RESPONSE.response_metadata_id,
        region_id=JITA.region_id,
        duration=90,
        is_buy_order=buy,
        issued=RECEIVED,
        location_id=station_id,
        min_volume=1,
        order_id=order_id,
        price=D(price),
        range="station",
        system_id=JITA.system_id,
        type_id=2398,
        volume_remain=volume,
        volume_total=max(volume, 1),
    )


def dataset(*, response: MarketOrdersResponse = RESPONSE) -> MarketOrdersDataset:
    """Include depth, another station, and an exhausted best-price order."""
    return MarketOrdersDataset(
        response_metadata_id=response.response_metadata_id,
        received_at=response.received_at,
        expires_at=response.expires_at,
        argus_expires_at=response.argus_expires_at,
        region_id=response.region_id,
        records={
            2398: BuySellOrders(
                buy_orders=(order(order_id=1, price="90", volume=100, buy=True),),
                sell_orders=(
                    order(order_id=2, price="100", volume=1),
                    order(order_id=3, price="110", volume=99),
                    order(
                        order_id=4,
                        price="1",
                        volume=1000,
                        station_id=JITA.station_id + 1,
                    ),
                    order(order_id=5, price="2", volume=0),
                ),
            )
        },
    )


def history_record(
    *, type_id: int = 2398, day: int = 16, volume: int = 125
) -> MarketHistoryRecord:
    """Create one day of synthetic Forge history."""
    return MarketHistoryRecord(
        received_at="2026-11-17T18:00:00Z",
        expires_at=None,
        argus_expires_at=None,
        region_id=JITA.region_id,
        type_id=type_id,
        average=D("123.45"),
        date=f"2026-11-{day:02}",
        highest=D("130"),
        lowest=D("120"),
        order_count=2,
        volume=volume,
    )


def regional_history(
    records: tuple[MarketHistoryRecord, ...],
) -> RegionalHistory:
    """Use one regional calendar window, not per-material anchors."""
    return RegionalHistory(
        window=select_history_window(
            newest_stored_date="2026-11-16", generation_date=date(2026, 11, 17)
        ),
        records=lambda type_id: tuple(r for r in records if r.type_id == type_id),
    )


def test_collects_station_five_percent_prices_for_the_whole_catalog() -> None:
    """PI references include all 83 types, even when one or both sides are absent."""
    result = collect_pi_market_inputs(
        catalog=load_catalog(),
        response=RESPONSE,
        orders=dataset(),
        history=None,
        generated_at=GENERATED,
    )

    assert result.hub is JITA
    assert len(result.materials) == 83
    assert [row.material.type_id for row in result.materials] == sorted(load_catalog())
    assert result.prices_for(MarketPriceBasis.JITA_BUY)[2398].unit_cost == 90
    sell = result.prices_for(MarketPriceBasis.JITA_SELL)
    assert sell[2398].unit_cost == 110
    assert sell[2398].source_id == "orders:7:60003760:jita-sell-5:2398"
    assert sell[2399].unit_cost is None
    assert sell[2399].unavailable_reason
    assert result.order_freshness == "current"
    assert result.order_expires_at == RESPONSE.argus_expires_at
    assert result.response is RESPONSE
    assert any("history" in warning.lower() for warning in result.warnings)


def test_history_preserves_eight_day_coverage_over_ten_calendar_days() -> None:
    """Eight days totaling 1000 units yield 100 regional units/day, not 125."""
    records = tuple(history_record(day=day) for day in range(9, 17))
    result = collect_pi_market_inputs(
        catalog=load_catalog(),
        response=RESPONSE,
        orders=dataset(),
        history=regional_history(records),
        generated_at=GENERATED,
    )
    row = next(row for row in result.materials if row.material.type_id == 2398)
    assert result.history_window is not None
    assert result.history_window.oldest_date == "2026-11-07"
    assert row.history.unit_cost == D("123.45")
    assert row.history_metrics is not None
    assert row.history_metrics.average_daily_volume == 100
    assert row.history_metrics.missing_days == 2
    assert row.history_metrics.received_at == "2026-11-17T18:00:00Z"
    assert result.prices_for(MarketPriceBasis.HISTORY)[2398] is row.history


def test_zero_volume_is_not_missing_history_or_a_free_price() -> None:
    """A known zero-volume day retains zero volume but no usable average price."""
    result = collect_pi_market_inputs(
        catalog=load_catalog(),
        response=RESPONSE,
        orders=dataset(),
        history=regional_history((history_record(volume=0),)),
        generated_at=GENERATED,
    )
    rows = {row.material.type_id: row for row in result.materials}
    zero = rows[2398]
    missing = rows[2399]
    assert zero.history.unit_cost is None
    assert zero.history.unavailable_reason is not None
    assert "zero" in zero.history.unavailable_reason.lower()
    assert zero.history_metrics is not None
    assert zero.history_metrics.average_daily_volume == 0
    assert missing.history.unit_cost is None
    assert missing.history_metrics is not None
    assert missing.history_metrics.average_daily_volume is None


def test_history_uses_volume_weighted_prices() -> None:
    """The source quote reuses the weighted helper, not an average of daily means."""
    records = (
        replace(history_record(day=16, volume=100), average=D("100")),
        replace(history_record(day=15, volume=300), average=D("200")),
    )
    result = collect_pi_market_inputs(
        catalog=load_catalog(),
        response=RESPONSE,
        orders=dataset(),
        history=regional_history(records),
        generated_at=GENERATED,
    )
    assert result.prices_for(MarketPriceBasis.HISTORY)[2398].unit_cost == 175


def test_stale_history_warns_without_discarding_its_price() -> None:
    """A common regional anchor can leave an individual material's history stale."""
    result = collect_pi_market_inputs(
        catalog=load_catalog(),
        response=RESPONSE,
        orders=dataset(),
        history=regional_history((history_record(day=7),)),
        generated_at=GENERATED,
    )
    assert result.prices_for(MarketPriceBasis.HISTORY)[2398].unit_cost == D("123.45")
    assert any("Stale The Forge history" in warning for warning in result.warnings)


def test_history_lookup_cannot_return_a_different_region() -> None:
    """Incorrect history scope fails instead of producing a mislabeled Forge quote."""
    valid = regional_history(())
    wrong = replace(history_record(), region_id=10000032)
    with pytest.raises(ValueError, match="scope"):
        collect_pi_market_inputs(
            catalog=load_catalog(),
            response=RESPONSE,
            orders=dataset(),
            history=RegionalHistory(
                window=valid.window,
                records=lambda type_id: (wrong,) if type_id == wrong.type_id else (),
            ),
            generated_at=GENERATED,
        )


@pytest.mark.parametrize(
    ("expiry", "expected"), [("2026-11-17T19:30:00Z", "expired"), (None, "unknown")]
)
def test_order_freshness_is_explicit(expiry: str | None, expected: str) -> None:
    """Expired and unknown-expiry inputs remain usable and warn without refresh."""
    response = replace(RESPONSE, expires_at=expiry, argus_expires_at=None)
    result = collect_pi_market_inputs(
        catalog=load_catalog(),
        response=response,
        orders=dataset(response=response),
        history=None,
        generated_at=GENERATED,
    )
    assert result.order_freshness == expected
    assert result.prices_for(MarketPriceBasis.JITA_SELL)[2398].unit_cost == 110
    assert any("order" in warning.lower() for warning in result.warnings)


def test_collector_rejects_mixed_snapshot_provenance() -> None:
    """The chosen order response cannot be paired with another response's dataset."""
    with pytest.raises(ValueError, match="response_metadata_id"):
        collect_pi_market_inputs(
            catalog=load_catalog(),
            response=replace(RESPONSE, response_metadata_id=8),
            orders=dataset(),
            history=None,
            generated_at=GENERATED,
        )


def test_jita_is_resolved_from_the_hub_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """No other hub's metadata or data is needed, and Jita need not be first."""
    custom_jita = replace(JITA, station_id=JITA.station_id + 1)
    monkeypatch.setattr(
        market_hubs, "MARKET_HUBS", [market_hubs.MARKET_HUBS[2], custom_jita]
    )
    result = collect_pi_market_inputs(
        catalog=load_catalog(),
        response=RESPONSE,
        orders=dataset(),
        history=None,
        generated_at=GENERATED,
    )
    assert result.hub is custom_jita
    assert result.prices_for(MarketPriceBasis.JITA_SELL)[2398].unit_cost == 1
