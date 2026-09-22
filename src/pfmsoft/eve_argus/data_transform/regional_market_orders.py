"""Transforms ESI region market orders to Argus region market orders."""

from collections.abc import Iterable
from dataclasses import asdict
from decimal import Decimal

from pfmsoft.eve_argus.models.esi import argus_response_models as ARM
from pfmsoft.eve_argus.models.esi import esi_response_models as ERM


def transform_region_market_orders_esi(
    region_market_orders: ERM.GetMarketsRegionIdOrders,
) -> ARM.RegionMarketOrders:
    """Transforms ESI region market orders to Argus region market orders.

    Args:
        region_market_orders: The ESI region market orders to transform.

    Returns:
        The transformed Argus region market orders.
    """
    orders_by_type: dict[int, ARM.DividedOrders] = {}
    for order in _convert_order(region_market_orders.orders):
        type_orders = orders_by_type.setdefault(order.type_id, ARM.DividedOrders())
        order_detail = ARM.MarketOrderDetail(**asdict(order))
        if order.is_buy_order:
            type_orders.buy_orders.append(order_detail)
        else:
            type_orders.sell_orders.append(order_detail)

    return ARM.RegionMarketOrders(
        received_at=region_market_orders.received_at,
        expires_at=region_market_orders.expires_at,
        region_id=region_market_orders.region_id,
        orders=orders_by_type,
    )


def _convert_order(
    orders: Iterable[ERM.GetMarketsRegionIdOrdersDetail],
) -> Iterable[ARM.MarketOrderDetail]:
    for order in orders:
        yield ARM.MarketOrderDetail(
            duration=order.duration,
            is_buy_order=order.is_buy_order,
            issued=order.issued,
            location_id=order.location_id,
            min_volume=order.min_volume,
            order_id=order.order_id,
            price=Decimal(order.price),
            range=order.range,
            system_id=order.system_id,
            type_id=order.type_id,
            volume_remain=order.volume_remain,
            volume_total=order.volume_total,
        )


def transform_region_market_orders_db(
    region_id: int,
    received_at: str,
    expires_at: str,
    orders: list[ARM.MarketOrderDetail],
) -> ARM.RegionMarketOrders:
    """Transforms a list of region market orders from the database to Argus region market orders.

    Args:
        region_id: The ID of the region.
        received_at: The timestamp when the data was received.
        expires_at: The timestamp when the data expires.
        orders: The list of market order details.

    Returns:
        The transformed Argus region market orders.
    """
    orders_by_type: dict[int, ARM.DividedOrders] = {}
    for order in orders:
        type_orders = orders_by_type.setdefault(order.type_id, ARM.DividedOrders())
        if order.is_buy_order:
            type_orders.buy_orders.append(order)
        else:
            type_orders.sell_orders.append(order)

    return ARM.RegionMarketOrders(
        received_at=received_at,
        expires_at=expires_at,
        region_id=region_id,
        orders=orders_by_type,
    )
