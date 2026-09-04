"""Tests for regional market order transformations."""

from pfmsoft.eve_argus.data_transform.regional_market_orders import (
    transform_region_market_orders,
)
from pfmsoft.eve_argus.models.esi.argus_response_models import MarketOrderDetail
from pfmsoft.eve_argus.models.esi.esi_response_models import (
    GetMarketsRegionIdOrders,
    GetMarketsRegionIdOrdersDetail,
)


def test_transform_region_market_orders_groups_orders_by_type():
    """ESI order lists should become buy/sell buckets keyed by type ID."""
    buy_order = GetMarketsRegionIdOrdersDetail(
        duration=90,
        is_buy_order=True,
        issued="2024-01-01T00:00:00Z",
        location_id=60003760,
        min_volume=1,
        order_id=101,
        price=10.5,
        range="station",
        system_id=30000142,
        type_id=34,
        volume_remain=5,
        volume_total=5,
    )
    sell_order = GetMarketsRegionIdOrdersDetail(
        duration=90,
        is_buy_order=False,
        issued="2024-01-01T00:00:00Z",
        location_id=60003760,
        min_volume=1,
        order_id=102,
        price=11.5,
        range="station",
        system_id=30000142,
        type_id=34,
        volume_remain=7,
        volume_total=7,
    )
    other_buy_order = GetMarketsRegionIdOrdersDetail(
        duration=30,
        is_buy_order=True,
        issued="2024-01-01T00:00:00Z",
        location_id=60003760,
        min_volume=1,
        order_id=103,
        price=9.75,
        range="station",
        system_id=30000142,
        type_id=35,
        volume_remain=2,
        volume_total=2,
    )

    response = GetMarketsRegionIdOrders(
        received_at="2024-01-01T00:00:00Z",
        expires_at=None,
        region_id=10000002,
        orders=[buy_order, sell_order, other_buy_order],
    )

    transformed = transform_region_market_orders(response)

    assert transformed.region_id == 10000002
    assert list(transformed.orders) == [34, 35]
    assert len(transformed.orders[34].buy_orders) == 1
    assert len(transformed.orders[34].sell_orders) == 1
    assert isinstance(transformed.orders[34].buy_orders[0], MarketOrderDetail)
    assert isinstance(transformed.orders[34].sell_orders[0], MarketOrderDetail)
    assert transformed.orders[34].buy_orders[0].order_id == 101
    assert transformed.orders[34].sell_orders[0].order_id == 102
    assert transformed.orders[35].buy_orders[0].type_id == 35
