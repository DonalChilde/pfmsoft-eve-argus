"""Transforms ESI region market orders to Argus region market orders."""

from dataclasses import asdict

from pfmsoft.eve_argus.models.esi.esi_argus import (
    DividedOrders,
    MarketOrderDetail,
    RegionMarketOrders,
)
from pfmsoft.eve_argus.models.esi.esi_response import GetMarketsRegionIdOrders


def transform_region_market_orders(
    esi_region_market_orders: GetMarketsRegionIdOrders,
) -> RegionMarketOrders:
    """Transforms ESI region market orders to Argus region market orders.

    Args:
        esi_region_market_orders: The ESI region market orders to transform.

    Returns:
        The transformed Argus region market orders.
    """
    orders_by_type: dict[int, DividedOrders] = {}
    for order in esi_region_market_orders.orders:
        type_orders = orders_by_type.setdefault(order.type_id, DividedOrders())
        order_detail = MarketOrderDetail(**asdict(order))
        if order.is_buy_order:
            type_orders.buy_orders.append(order_detail)
        else:
            type_orders.sell_orders.append(order_detail)

    return RegionMarketOrders(
        received_at=esi_region_market_orders.received_at,
        expires_at=esi_region_market_orders.expires_at,
        region_id=esi_region_market_orders.region_id,
        orders=orders_by_type,
    )
