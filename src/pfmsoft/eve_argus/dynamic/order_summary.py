"""Order summary generation."""

from collections.abc import Sequence
from decimal import Decimal

from pfmsoft.eve_argus.dynamic import models
from pfmsoft.eve_argus.helpers.currency import as_currency

FILTER_FACTOR_DEFAULT = Decimal("100.00")


def calculate_dataset_summaries(
    market_orders: models.MarketOrdersDataset,
    *,
    system_id: int | None = None,
    location_id: int | None = None,
    filter_factor: Decimal = FILTER_FACTOR_DEFAULT,
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
    validate_summary_options(
        system_id=system_id, location_id=location_id, filter_factor=filter_factor
    )

    def summarize(
        orders: Sequence[models.MarketOrderRecord], *, type_id: int, is_buy: bool
    ) -> models.OrderSummaryRecord | None:
        return calculate_order_summary(
            _scope_orders(orders, system_id=system_id, location_id=location_id),
            region_id=market_orders.region_id,
            type_id=type_id,
            system_id=system_id,
            location_id=location_id,
            is_buy_summary=is_buy,
            filter_factor=filter_factor,
        )

    records = {
        type_id: models.BuySellSummary(
            buy_summary=summarize(orders.buy_orders, type_id=type_id, is_buy=True),
            sell_summary=summarize(orders.sell_orders, type_id=type_id, is_buy=False),
        )
        for type_id, orders in market_orders.records.items()
    }

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


def validate_summary_options(
    *, system_id: int | None, location_id: int | None, filter_factor: Decimal
) -> None:
    """Validate the scope and outlier filter options for a summary calculation.

    Raises:
        ValueError: If both scopes are supplied or the factor is not greater than 1.
    """
    if system_id is not None and location_id is not None:
        raise ValueError(
            "Cannot specify both system_id and location_id. Choose one or neither."
        )
    if filter_factor <= Decimal("1"):
        raise ValueError("filter_factor must be greater than 1.0.")


def calculate_order_summary(
    orders: Sequence[models.MarketOrderRecord],
    *,
    region_id: int,
    type_id: int,
    system_id: int | None,
    location_id: int | None,
    is_buy_summary: bool,
    filter_factor: Decimal = FILTER_FACTOR_DEFAULT,
) -> models.OrderSummaryRecord | None:
    """Summarize one side of a book from orders already filtered to a scope.

    The orders need not be sorted, but every order must match the declared region,
    type, side, and scope, so that the record accurately describes its source.

    Args:
        orders: Pre-filtered orders for one type and side of the book.
        region_id: The region the orders belong to.
        type_id: The item type the orders belong to.
        system_id: The solar system scope of the orders, if any.
        location_id: The station or structure scope of the orders, if any.
        is_buy_summary: True to summarize buy orders, False for sell orders.
        filter_factor: Exclude buy prices below best / factor and sell prices above
            best * factor. Must be greater than 1.

    Returns:
        The summary, or None if there are no orders with remaining volume.

    Raises:
        ValueError: If the options are invalid or an order is outside the scope.
    """
    validate_summary_options(
        system_id=system_id, location_id=location_id, filter_factor=filter_factor
    )
    for order in orders:
        _validate_order(
            order,
            region_id=region_id,
            type_id=type_id,
            system_id=system_id,
            location_id=location_id,
            is_buy_summary=is_buy_summary,
        )

    sorted_orders = sorted(
        orders, key=lambda order: order.price, reverse=is_buy_summary
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
        region_id=region_id,
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


def _scope_orders(
    orders: Sequence[models.MarketOrderRecord],
    *,
    system_id: int | None,
    location_id: int | None,
) -> tuple[models.MarketOrderRecord, ...]:
    """Select the orders within an optional system or location scope."""
    return tuple(
        order
        for order in orders
        if (system_id is None or order.system_id == system_id)
        and (location_id is None or order.location_id == location_id)
    )


def _validate_order(
    order: models.MarketOrderRecord,
    *,
    region_id: int,
    type_id: int,
    system_id: int | None,
    location_id: int | None,
    is_buy_summary: bool,
) -> None:
    """Raise ValueError if an order does not belong to the summary being built."""
    if order.is_buy_order != is_buy_summary:
        raise ValueError(
            f"Order is_buy_order {order.is_buy_order} does not match summary type "
            f"{is_buy_summary}"
        )
    if order.type_id != type_id:
        raise ValueError("All orders must be of the same type_id.")
    if order.region_id != region_id:
        raise ValueError(
            f"Order {order.order_id} region_id {order.region_id} does not match "
            f"{region_id}."
        )
    if system_id is not None and order.system_id != system_id:
        raise ValueError(
            f"Order {order.order_id} system_id {order.system_id} does not match "
            f"{system_id}."
        )
    if location_id is not None and order.location_id != location_id:
        raise ValueError(
            f"Order {order.order_id} location_id {order.location_id} does not match "
            f"{location_id}."
        )
