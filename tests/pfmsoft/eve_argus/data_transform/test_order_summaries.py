"""Tests for market order summary calculations."""

import pytest

from pfmsoft.eve_argus.data_transform.order_summaries import (
    calculate_order_summary,
    calculate_order_summary_detail,
    calculate_summaries,
)
from pfmsoft.eve_argus.models.esi.esi_argus import (
    DividedOrders,
    MarketOrderDetail,
    RegionMarketOrders,
)


def order(
    order_id: int,
    *,
    price: float,
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
        price=price,
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


def test_calculate_order_summary_detail_filters_outliers_and_computes_depth() -> None:
    """Buy and sell summaries should use valid volume and the best 5% bucket."""
    orders = divided_orders()

    buy_result = calculate_order_summary_detail(34, orders.buy_orders, True, 10)
    sell_result = calculate_order_summary_detail(34, orders.sell_orders, False, 10)

    assert buy_result.total_items == 30
    assert buy_result.total_orders == 2
    assert buy_result.filtered_items == 30
    assert buy_result.filtered_orders == 1
    assert buy_result.avg_price == pytest.approx(93.3333333333)
    assert (buy_result.five_price, buy_result.five_orders, buy_result.five_items) == (
        100,
        1,
        10,
    )
    assert sell_result.total_items == 30
    assert sell_result.filtered_items == 30
    assert sell_result.avg_price == pytest.approx(116.6666666667)
    assert (
        sell_result.five_price,
        sell_result.five_orders,
        sell_result.five_items,
    ) == (110, 1, 10)


def test_calculate_order_summary_applies_system_and_location_filters() -> None:
    """Order summaries should scope both sides to the requested location."""
    orders = divided_orders()
    orders.buy_orders.append(
        order(7, price=80, volume=10, is_buy_order=True, location_id=60003761)
    )
    summary = calculate_order_summary(
        10000002,
        34,
        orders,
        location_id=60003760,
        filter_factor=10,
    )

    assert summary.location_id == 60003760
    assert summary.solar_system_id is None
    assert summary.buy_summary.total_items == 30


def test_calculate_summaries_builds_region_collection() -> None:
    """Collection calculation should preserve metadata and summarize each type."""
    region_orders = RegionMarketOrders(
        received_at="2025-01-01T00:00:00Z",
        expires_at=None,
        region_id=10000002,
        orders={34: divided_orders()},
    )

    result = calculate_summaries(region_orders, filter_factor=10)

    assert result.region_id == 10000002
    assert result.filter_factor == 10
    assert result.summaries[34].buy_summary.total_orders == 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"solar_system_id": 30000142, "location_id": 60003760},
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


@pytest.mark.parametrize(
    ("orders", "is_buy_summary", "message"),
    [
        ([order(1, price=100, volume=1, is_buy_order=False)], True, "does not match"),
        (
            [order(1, price=100, volume=1, is_buy_order=True, type_id=35)],
            True,
            "same type_id",
        ),
    ],
)
def test_calculate_order_summary_detail_rejects_mismatched_orders(
    orders: list[MarketOrderDetail],
    is_buy_summary: bool,
    message: str,
) -> None:
    """A side summary should contain only orders for its declared side and type."""
    with pytest.raises(ValueError, match=message):
        calculate_order_summary_detail(34, orders, is_buy_summary)
