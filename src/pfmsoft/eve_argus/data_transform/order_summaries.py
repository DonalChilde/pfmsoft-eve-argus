"""Calculate summaries for market orders in a GetMarketsRegionIdOrders response."""

from collections.abc import Sequence
from typing import Literal

from pfmsoft.eve_argus.models.esi import argus_response_models


def calculate_summaries(
    region_orders: argus_response_models.RegionMarketOrders,
    solar_system_id: int | None = None,
    location_id: int | None = None,
    filter_factor: float = 100.0,
) -> argus_response_models.OrderSummaries:
    """Summarize buy and sell depth for one region, or for a system/location subset.

    Each item summary is built from the filtered valid orders for that side of the book.
    The outlier filter removes extreme prices before the 5% depth threshold is computed.
    For buy orders, prices lower than the best price divided by ``filter_factor`` are
    discarded. For sell orders, prices higher than the best price multiplied by
    ``filter_factor`` are discarded. ``filter_factor`` must be greater than 1.0.

    Once the valid orders are selected, the algorithm calculates the price threshold at
    which 5% of the valid volume is available. This threshold is reported as
    ``five_price`` and the volume available at or better than that price is reported as
    ``five_items``.

    Args:
        region_orders: The region-wide order payload to summarize.
        solar_system_id: Optional solar system ID used to limit the summary to a single
            solar system. Cannot be combined with ``location_id``.
        location_id: Optional location ID used to limit the summary to a single station or
            container. Cannot be combined with ``solar_system_id``.
        filter_factor: Outlier-removal multiplier. Buy orders below
            ``best_buy_price / filter_factor`` are excluded, and sell orders above
            ``best_sell_price * filter_factor`` are excluded. Must be greater than 1.0.

    Returns:
        An ``OrderSummaries`` object containing a summary for each item type.

    Raises:
        ValueError: If both ``solar_system_id`` and ``location_id`` are supplied, or if
            ``filter_factor`` is less than or equal to 1.0.
    """
    if solar_system_id is not None and location_id is not None:
        raise ValueError(
            "Cannot specify both solar_system_id and location_id. Choose one or neither."
        )
    if filter_factor <= 1.0:
        raise ValueError("filter_factor must be greater than 1.0.")
    summaries = argus_response_models.OrderSummaries(
        received_at=region_orders.received_at,
        expires_at=region_orders.expires_at,
        region_id=region_orders.region_id,
        solar_system_id=solar_system_id,
        location_id=location_id,
        filter_factor=filter_factor,
        summaries={},
    )
    for type_id, divided_orders in region_orders.orders.items():
        summary = calculate_order_summary(
            region_id=region_orders.region_id,
            type_id=type_id,
            collected_orders=divided_orders,
            solar_system_id=solar_system_id,
            location_id=location_id,
            filter_factor=filter_factor,
        )
        summaries.summaries[type_id] = summary
    return summaries


def calculate_order_summary(
    region_id: int,
    type_id: int,
    collected_orders: argus_response_models.DividedOrders,
    solar_system_id: int | None = None,
    location_id: int | None = None,
    filter_factor: float = 100.0,
) -> argus_response_models.OrderSummary:
    """Summarize the buy and sell depth for one item type.

    The function first narrows the order set to the requested scope: whole region,
    specific solar system, or specific location. It then computes a buy-side and sell-side
    summary using the same outlier filter and 5% depth algorithm.

    Args:
        region_id: The region containing the orders.
        type_id: The item type being summarized.
        collected_orders: The buy and sell orders for the specified item type.
        solar_system_id: Optional solar system filter. If provided, only orders from that
            solar system are included.
        location_id: Optional location filter. If provided, only orders from that location
            are included.
        filter_factor: Outlier-removal multiplier. Buy orders below
            ``best_buy_price / filter_factor`` are excluded, and sell orders above
            ``best_sell_price * filter_factor`` are excluded.

    Returns:
        An ``OrderSummary`` containing the buy and sell summary items for the item type.
    """
    location_filter: Literal["solar_system", "location", "none"]
    if solar_system_id is not None:
        location_filter = "solar_system"
    elif location_id is not None:
        location_filter = "location"
    else:
        location_filter = "none"
    match location_filter:
        case "solar_system":
            buy_orders = [
                o for o in collected_orders.buy_orders if o.system_id == solar_system_id
            ]
            sell_orders = [
                o
                for o in collected_orders.sell_orders
                if o.system_id == solar_system_id
            ]
        case "location":
            buy_orders = [
                o for o in collected_orders.buy_orders if o.location_id == location_id
            ]
            sell_orders = [
                o for o in collected_orders.sell_orders if o.location_id == location_id
            ]
        case "none":
            buy_orders = collected_orders.buy_orders
            sell_orders = collected_orders.sell_orders

    buy_summary = calculate_order_summary_detail(
        type_id=type_id,
        orders=buy_orders,
        is_buy_summary=True,
        filter_factor=filter_factor,
    )
    sell_summary = calculate_order_summary_detail(
        type_id=type_id,
        orders=sell_orders,
        is_buy_summary=False,
        filter_factor=filter_factor,
    )
    return argus_response_models.OrderSummary(
        region_id=region_id,
        solar_system_id=solar_system_id,
        location_id=location_id,
        type_id=type_id,
        buy_summary=buy_summary,
        sell_summary=sell_summary,
    )


def calculate_order_summary_detail(
    type_id: int,
    orders: Sequence[argus_response_models.MarketOrderDetail],
    is_buy_summary: bool,
    filter_factor: float = 100.0,
) -> argus_response_models.OrderSummaryItem:
    """Calculate a summary for one side of a market for a single item type.

    The summary is computed from a list of orders that are already known to be the same
    item type and same ordering side (buy or sell). The function first drops outlier
    orders using ``filter_factor``, then calculates the price threshold at which 5% of
    the remaining valid volume is available. ``five_price`` is the last price included
    when walking the best-priced orders until the cumulative volume reaches or exceeds
    5% of the total valid volume.

    For buy orders, the valid book is ordered from highest price to lowest price and the
    cutoff is the best price divided by ``filter_factor``. For sell orders, the valid book
    is ordered from lowest price to highest price and the cutoff is the best price
    multiplied by ``filter_factor``.

    Args:
        type_id: The item type being summarized.
        orders: A sequence of market orders for one item type and one side of the book.
        is_buy_summary: ``True`` to summarize buy orders; ``False`` to summarize sell
            orders.
        filter_factor: Outlier-removal multiplier. Buy orders below
            ``best_buy_price / filter_factor`` are excluded, and sell orders above
            ``best_sell_price * filter_factor`` are excluded. Must be greater than 1.0.

    Returns:
        An ``OrderSummaryItem`` containing the aggregate metrics for that side of the book.

    Raises:
        ValueError: If orders contain mismatched ``is_buy_order`` values or multiple
            ``type_id`` values.

    Note:
        The 5% depth bucket is computed from the filtered valid orders only. The returned
        ``five_items`` value is the volume available at or better than the threshold price,
        while ``five_orders`` is the count of orders in the threshold bucket used to reach
        the 5% volume target.
    """
    # Walk the best-priced orders first so the 5% depth threshold reflects the current
    # top-of-book depth, not the entire unfiltered order list.
    if is_buy_summary:
        orders = sorted(orders, key=lambda o: o.price, reverse=True)
    else:
        orders = sorted(orders, key=lambda o: o.price)
    five_price = lowest = highest = avg_price = 0.0
    total_items = total_orders = five_orders_count = 0
    five_items = filtered_items = filtered_orders = 0

    # Check that all orders have the same is_buy_order and type_id.
    for order in orders:
        if order.is_buy_order != is_buy_summary:
            msg = f"Order is_buy_order {order.is_buy_order} does not match summary type {is_buy_summary}"
            raise ValueError(msg)
        if order.type_id != type_id:
            msg = "All orders must be of the same type_id."
            raise ValueError(msg)

    # Filter out extreme tail orders before calculating the depth threshold. This keeps
    # a small number of absurd outliers from distorting the price and volume metrics.
    if is_buy_summary:
        price_cutoff = orders[0].price / filter_factor if orders else 0.0
        valid_orders = [o for o in orders if o.price >= price_cutoff]
        excluded_orders = [o for o in orders if o.price < price_cutoff]
    else:
        price_cutoff = orders[0].price * filter_factor if orders else 0.0
        valid_orders = [o for o in orders if o.price <= price_cutoff]
        excluded_orders = [o for o in orders if o.price > price_cutoff]
    highest = max(o.price for o in valid_orders) if valid_orders else 0.0
    lowest = min(o.price for o in valid_orders) if valid_orders else 0.0
    total_volume = sum(o.volume_remain for o in valid_orders)
    # Volume-weighted average price is the weighted mean of all valid orders.
    avg_price = (
        sum(o.volume_remain * o.price for o in valid_orders) / total_volume
        if valid_orders
        else 0.0
    )
    total_items = sum(o.volume_remain for o in valid_orders)
    total_orders = len(valid_orders)
    filtered_items = sum(o.volume_remain for o in excluded_orders)
    filtered_orders = len(excluded_orders)
    five_percent_of_items = total_items * 0.05
    five_percent_orders: list[argus_response_models.MarketOrderDetail] = []
    items = 0
    for order in valid_orders:
        # Include the order if the cumulative volume is still at or below the 5% target.
        # The last included order establishes the threshold price.
        if items <= five_percent_of_items:
            five_percent_orders.append(order)
            items += order.volume_remain
        else:
            break

    five_price = five_percent_orders[-1].price if five_percent_orders else 0.0
    five_orders_count = len(five_percent_orders)
    if is_buy_summary:
        # Buy threshold: the 5% bucket includes all valid orders at or above the threshold.
        five_items = (
            sum(o.volume_remain for o in five_percent_orders if o.price >= five_price)
            if five_percent_orders
            else 0
        )
    else:
        # Sell threshold: the 5% bucket includes all valid orders at or below the threshold.
        five_items = (
            sum(o.volume_remain for o in valid_orders if o.price <= five_price)
            if five_percent_orders
            else 0
        )

    # summary = esi_argus.OrderSummaryItem(
    #     type_id=type_id,
    #     is_buy_summary=is_buy_summary,
    #     five_price=five_price,
    #     five_orders=five_orders_count,
    #     five_items=five_items,
    #     lowest=lowest,
    #     highest=highest,
    #     total_items=total_items,
    #     total_orders=total_orders,
    #     avg_price=avg_price,
    #     filtered_items=filtered_items,
    #     filtered_orders=filtered_orders,
    # )

    summary = argus_response_models.OrderSummaryItem(
        type_id=type_id,
        is_buy_summary=is_buy_summary,
        five_price=five_price,
        five_orders=five_orders_count,
        five_items=five_items,
        lowest=lowest,
        highest=highest,
        total_items=total_items,
        total_orders=total_orders,
        avg_price=avg_price,
        filtered_items=filtered_items,
        filtered_orders=filtered_orders,
    )

    return summary
