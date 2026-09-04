"""Transforms ESI region market orders to Argus region market orders."""

from dataclasses import asdict

from pfmsoft.eve_argus.models.esi import argus_response_models, esi_response_models


def transform_region_market_orders(
    region_market_orders: esi_response_models.GetMarketsRegionIdOrders,
) -> argus_response_models.RegionMarketOrders:
    """Transforms ESI region market orders to Argus region market orders.

    Args:
        region_market_orders: The ESI region market orders to transform.

    Returns:
        The transformed Argus region market orders.
    """
    orders_by_type: dict[int, argus_response_models.DividedOrders] = {}
    for order in region_market_orders.orders:
        type_orders = orders_by_type.setdefault(
            order.type_id, argus_response_models.DividedOrders()
        )
        order_detail = argus_response_models.MarketOrderDetail(**asdict(order))
        if order.is_buy_order:
            type_orders.buy_orders.append(order_detail)
        else:
            type_orders.sell_orders.append(order_detail)

    return argus_response_models.RegionMarketOrders(
        received_at=region_market_orders.received_at,
        expires_at=region_market_orders.expires_at,
        region_id=region_market_orders.region_id,
        orders=orders_by_type,
    )
