"""Order summary generation."""

from collections.abc import Sequence
from decimal import Decimal

from pfmsoft.eve_argus.dynamic.db import models
from pfmsoft.eve_argus.helpers.currency import as_currency


def calculate_summaries(
    market_orders: models.MarketOrdersDataset,
    *,
    system_id: int | None = None,
    location_id: int | None = None,
    filter_factor: Decimal = Decimal("100.00"),
) -> models.OrderSummaryDataset:
    """Summarize the buy and sell orders for each type in a market orders dataset.

    Args:
        market_orders: Source orders, including their response metadata.
        system_id: Limit the calculation to one solar system.
        location_id: Limit the calculation to one station or structure.
        filter_factor: Exclude buy prices below best / factor and sell prices above
            best * factor. Must be greater than 1.

    Returns:
        Summaries linked to the source response metadata ID.

    Raises:
        ValueError: If both scopes are supplied, the factor is invalid, or an order
            has the wrong type or side.
    """
    if system_id is not None and location_id is not None:
        raise ValueError(
            "Cannot specify both system_id and location_id. Choose one or neither."
        )
    if filter_factor <= Decimal("1"):
        raise ValueError("filter_factor must be greater than 1.0.")

    records: dict[int, models.BuySellSummary] = {}
    for type_id, divided_orders in market_orders.records.items():
        records[type_id] = models.BuySellSummary(
            buy_summary=_calculate_side(
                orders=divided_orders.buy_orders,
                market_orders=market_orders,
                type_id=type_id,
                system_id=system_id,
                location_id=location_id,
                filter_factor=filter_factor,
                is_buy_summary=True,
            ),
            sell_summary=_calculate_side(
                orders=divided_orders.sell_orders,
                market_orders=market_orders,
                type_id=type_id,
                system_id=system_id,
                location_id=location_id,
                filter_factor=filter_factor,
                is_buy_summary=False,
            ),
        )

    return models.OrderSummaryDataset(
        response_metadata_id=market_orders.response_metadata_id,
        received_at=market_orders.received_at,
        expires_at=market_orders.expires_at,
        argus_expires_at=market_orders.argus_expires_at,
        region_id=market_orders.region_id,
        system_id=system_id,
        location_id=location_id,
        records=records,
    )


def _calculate_side(
    *,
    orders: Sequence[models.MarketOrderRecord],
    market_orders: models.MarketOrdersDataset,
    type_id: int,
    system_id: int | None,
    location_id: int | None,
    filter_factor: Decimal,
    is_buy_summary: bool,
) -> models.OrderSummaryRecord | None:
    """Summarize one side of a book after applying scope and outlier filters."""
    scoped_orders = [
        order
        for order in orders
        if (system_id is None or order.system_id == system_id)
        and (location_id is None or order.location_id == location_id)
    ]
    for order in scoped_orders:
        if order.is_buy_order != is_buy_summary:
            raise ValueError(
                f"Order is_buy_order {order.is_buy_order} does not match summary type "
                f"{is_buy_summary}"
            )
        if order.type_id != type_id:
            raise ValueError("All orders must be of the same type_id.")

    sorted_orders = sorted(
        scoped_orders, key=lambda order: order.price, reverse=is_buy_summary
    )
    if not sorted_orders:
        return None

    best_price = sorted_orders[0].price
    cutoff = (
        best_price / filter_factor if is_buy_summary else best_price * filter_factor
    )
    valid_orders = [
        order
        for order in sorted_orders
        if (order.price >= cutoff if is_buy_summary else order.price <= cutoff)
    ]
    excluded_orders = [
        order
        for order in sorted_orders
        if (order.price < cutoff if is_buy_summary else order.price > cutoff)
    ]
    total_items = sum(order.volume_remain for order in valid_orders)
    if total_items <= 0:
        return None

    target_items = Decimal(total_items) * Decimal("0.05")
    cumulative_items = 0
    five_price = valid_orders[-1].price
    for order in valid_orders:
        cumulative_items += order.volume_remain
        if cumulative_items >= target_items:
            five_price = order.price
            break

    depth_orders = [
        order
        for order in valid_orders
        if (order.price >= five_price if is_buy_summary else order.price <= five_price)
    ]
    average = (
        sum(
            (order.volume_remain * order.price for order in valid_orders),
            start=Decimal(),
        )
        / total_items
    )
    return models.OrderSummaryRecord(
        response_metadata_id=market_orders.response_metadata_id,
        region_id=market_orders.region_id,
        type_id=type_id,
        system_id=system_id,
        location_id=location_id,
        is_buy_summary=is_buy_summary,
        five_price=as_currency(five_price),
        five_orders=len(depth_orders),
        five_items=sum(order.volume_remain for order in depth_orders),
        lowest=as_currency(min(order.price for order in valid_orders)),
        highest=as_currency(max(order.price for order in valid_orders)),
        total_items=total_items,
        total_orders=len(valid_orders),
        average=as_currency(average),
        filtered_items=sum(order.volume_remain for order in excluded_orders),
        filtered_orders=len(excluded_orders),
    )
