"""Tests for market order summary calculations."""

import json
from decimal import Decimal

import pytest

from pfmsoft.eve_argus.data_transform.order_summaries import (
    OrderSummaryReport,
    calculate_order_summary,
    calculate_summaries,
)
from pfmsoft.eve_argus.models.esi.argus_response_models import (
    DividedOrders,
    MarketOrderDetail,
    RegionMarketOrders,
)


def order(
    order_id: int,
    *,
    price: Decimal | float | int,
    volume: int,
    is_buy_order: bool,
    system_id: int = 30000142,
    location_id: int = 60003760,
    type_id: int = 34,
) -> MarketOrderDetail:
    """Build one Argus market order."""
    return MarketOrderDetail(
        duration=90,
        is_buy_order=is_buy_order,
        issued="2025-01-01T00:00:00Z",
        location_id=location_id,
        min_volume=1,
        order_id=order_id,
        price=Decimal(str(price)),
        range="station",
        system_id=system_id,
        type_id=type_id,
        volume_remain=volume,
        volume_total=volume,
    )


def divided_orders() -> DividedOrders:
    """Build buy and sell books with one outlier on each side."""
    return DividedOrders(
        buy_orders=[
            order(1, price=100, volume=10, is_buy_order=True),
            order(2, price=90, volume=20, is_buy_order=True),
            order(3, price=5, volume=30, is_buy_order=True),
        ],
        sell_orders=[
            order(4, price=110, volume=10, is_buy_order=False),
            order(5, price=120, volume=20, is_buy_order=False),
            order(6, price=1200, volume=30, is_buy_order=False),
        ],
    )


def test_calculate_order_summary_filters_outliers_and_computes_depth() -> None:
    """Buy and sell summaries should use valid volume and the best 5% bucket."""
    result = calculate_order_summary(
        region_id=10000002,
        type_id=34,
        collected_orders=divided_orders(),
        filter_factor=Decimal("10"),
    )

    assert result.buy_summary is not None
    assert result.sell_summary is not None
    assert isinstance(result.buy_summary.five_price, Decimal)
    assert result.buy_summary.total_items == 30
    assert result.buy_summary.total_orders == 2
    assert result.buy_summary.filtered_items == 30
    assert result.buy_summary.filtered_orders == 1
    assert result.buy_summary.average == Decimal("93.33")
    assert (
        result.buy_summary.five_price,
        result.buy_summary.five_orders,
        result.buy_summary.five_items,
    ) == (
        Decimal("100"),
        1,
        10,
    )
    assert result.sell_summary.total_items == 30
    assert result.sell_summary.filtered_items == 30
    assert result.sell_summary.average == Decimal("116.67")
    assert (
        result.sell_summary.five_price,
        result.sell_summary.five_orders,
        result.sell_summary.five_items,
    ) == (Decimal("110"), 1, 10)


def test_calculate_order_summary_applies_system_and_location_filters() -> None:
    """Order summaries should scope both sides to the requested location."""
    orders = divided_orders()
    orders.buy_orders.append(
        order(7, price=80, volume=10, is_buy_order=True, location_id=60003761)
    )
    summary = calculate_order_summary(
        region_id=10000002,
        type_id=34,
        collected_orders=orders,
        location_id=60003760,
        filter_factor=Decimal("10"),
    )

    assert summary.buy_summary is not None
    assert summary.buy_summary.region_id == 10000002
    assert summary.buy_summary.system_id is None
    assert summary.buy_summary.location_id == 60003760
    assert summary.buy_summary.total_items == 30


def test_calculate_summaries_builds_region_collection() -> None:
    """Collection calculation should preserve metadata and summarize each type."""
    region_orders = RegionMarketOrders(
        received_at="2025-01-01T00:00:00Z",
        expires_at=None,
        region_id=10000002,
        orders={34: divided_orders()},
    )

    result = calculate_summaries(region_orders, filter_factor=Decimal("10"))

    assert result.region_id == 10000002
    assert result.system_id is None
    assert result.location_id is None
    assert result.summaries[34].buy_summary is not None
    assert result.summaries[34].buy_summary.total_orders == 2


def test_calculate_order_summary_is_independent_of_input_order() -> None:
    """Depth calculations should always walk orders from the best price."""
    orders = divided_orders()
    orders.buy_orders.reverse()
    orders.sell_orders.reverse()

    result = calculate_order_summary(
        region_id=10000002,
        type_id=34,
        collected_orders=orders,
        filter_factor=Decimal("10"),
    )

    assert result.buy_5 == Decimal("100")
    assert result.sell_5 == Decimal("110")


def test_calculate_order_summary_includes_threshold_price_ties() -> None:
    """Depth counts should include every order at the threshold price."""
    orders = DividedOrders(
        buy_orders=[
            order(1, price=99, volume=100, is_buy_order=True),
            order(2, price=100, volume=5, is_buy_order=True),
            order(3, price=100, volume=5, is_buy_order=True),
        ],
        sell_orders=[
            order(4, price=101, volume=100, is_buy_order=False),
            order(5, price=100, volume=5, is_buy_order=False),
            order(6, price=100, volume=5, is_buy_order=False),
        ],
    )

    result = calculate_order_summary(
        region_id=10000002,
        type_id=34,
        collected_orders=orders,
    )

    assert result.buy_summary is not None
    assert result.sell_summary is not None
    assert (
        result.buy_summary.five_price,
        result.buy_summary.five_orders,
        result.buy_summary.five_items,
    ) == (Decimal("100"), 2, 10)
    assert (
        result.sell_summary.five_price,
        result.sell_summary.five_orders,
        result.sell_summary.five_items,
    ) == (Decimal("100"), 2, 10)


def test_calculate_order_summary_stops_at_exact_five_percent() -> None:
    """An order reaching exactly 5% should establish the depth threshold."""
    orders = DividedOrders(
        buy_orders=[
            order(1, price=100, volume=5, is_buy_order=True),
            order(2, price=90, volume=95, is_buy_order=True),
        ],
    )

    result = calculate_order_summary(
        region_id=10000002,
        type_id=34,
        collected_orders=orders,
    )

    assert result.buy_summary is not None
    assert result.buy_summary.five_price == Decimal("100")
    assert result.buy_summary.five_orders == 1
    assert result.buy_summary.five_items == 5
    assert result.sell_summary is None


@pytest.mark.parametrize("volume", [0, -1])
def test_calculate_order_summary_returns_none_for_nonpositive_total(
    volume: int,
) -> None:
    """A side without positive total volume should not produce a summary."""
    orders = DividedOrders(
        buy_orders=[order(1, price=100, volume=volume, is_buy_order=True)]
    )

    result = calculate_order_summary(
        region_id=10000002,
        type_id=34,
        collected_orders=orders,
    )

    assert result.buy_summary is None
    assert result.sell_summary is None


def test_order_summary_report_round_trips_without_filter_factor() -> None:
    """The new report schema should round-trip without calculation settings."""
    region_orders = RegionMarketOrders(
        received_at="2025-01-01T00:00:00Z",
        expires_at=None,
        region_id=10000002,
        orders={34: divided_orders()},
    )
    result = calculate_summaries(
        region_orders,
        system_id=30000142,
        filter_factor=Decimal("10"),
    )

    serialized = result.serialize()
    restored = OrderSummaryReport.deserialize(serialized)

    assert "filter_factor" not in json.loads(serialized)
    assert restored == result
    assert restored.summaries[34].buy_summary is not None
    assert restored.summaries[34].buy_summary.system_id == 30000142


def test_order_summary_report_serializes_currency_with_two_decimal_places() -> None:
    """Serialized monetary fields should use fixed two-decimal currency strings."""
    region_orders = RegionMarketOrders(
        received_at="2025-01-01T00:00:00Z",
        expires_at=None,
        region_id=10000002,
        orders={34: divided_orders()},
    )

    serialized = json.loads(
        calculate_summaries(
            region_orders,
            filter_factor=Decimal("10"),
        ).serialize()
    )
    buy_summary = serialized["summaries"]["34"]["buy_summary"]

    assert buy_summary["five_price"] == "100.00"
    assert buy_summary["lowest"] == "90.00"
    assert buy_summary["highest"] == "100.00"
    assert buy_summary["average"] == "93.33"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"system_id": 30000142, "location_id": 60003760},
        {"filter_factor": 1},
    ],
)
def test_calculate_summaries_rejects_conflicting_scope_or_filter(kwargs: dict) -> None:
    """Summary collection should reject ambiguous scope and invalid filter factors."""
    region_orders = RegionMarketOrders(
        received_at="2025-01-01T00:00:00Z",
        expires_at=None,
        region_id=10000002,
        orders={},
    )

    with pytest.raises(ValueError):
        calculate_summaries(region_orders, **kwargs)


@pytest.mark.parametrize("filter_factor", [Decimal("1"), Decimal("0")])
def test_calculate_order_summary_rejects_invalid_filter_factor(
    filter_factor: Decimal,
) -> None:
    """The item-level public API should reject invalid filter factors."""
    with pytest.raises(ValueError, match="greater than 1"):
        calculate_order_summary(
            region_id=10000002,
            type_id=34,
            collected_orders=divided_orders(),
            filter_factor=filter_factor,
        )


@pytest.mark.parametrize(
    ("orders", "message"),
    [
        ([order(1, price=100, volume=1, is_buy_order=False)], "does not match"),
        (
            [order(1, price=100, volume=1, is_buy_order=True, type_id=35)],
            "same type_id",
        ),
    ],
)
def test_calculate_order_summary_rejects_mismatched_orders(
    orders: list[MarketOrderDetail],
    message: str,
) -> None:
    """A side summary should contain only orders for its declared side and type."""
    with pytest.raises(ValueError, match=message):
        calculate_order_summary(
            region_id=10000002,
            type_id=34,
            collected_orders=DividedOrders(buy_orders=orders),
        )
