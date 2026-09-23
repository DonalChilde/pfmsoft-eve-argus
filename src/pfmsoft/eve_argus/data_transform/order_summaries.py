"""Calculate summaries for market orders in a GetMarketsRegionIdOrders response."""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, Self

from pydantic import RootModel
from whenever import Instant

from pfmsoft.eve_argus.helpers.currency import as_currency
from pfmsoft.eve_argus.models.esi import argus_response_models as ARM


class Serializable(Protocol):
    """Defines JSON serialization for report models."""

    def serialize(self, indent: int | None = 2) -> str:
        """Serialize the object to a JSON string."""
        raise NotImplementedError

    @classmethod
    def deserialize(cls, data: str) -> Self:
        """Deserialize the object from a JSON string."""
        raise NotImplementedError


@dataclass(slots=True, kw_only=True)
class TimeStamped:
    """Provides access to ESI response timestamps."""

    received_at: str
    expires_at: str | None

    @property
    def expires_at_instant(self) -> Instant | None:
        """Return the expiration timestamp, if available."""
        return Instant.parse_iso(self.expires_at) if self.expires_at else None

    @property
    def received_at_instant(self) -> Instant:
        """Return the timestamp when the ESI data was fetched."""
        return Instant.parse_iso(self.received_at)


@dataclass(slots=True, kw_only=True)
class OrderSummaryItem:
    """Represents one side of the market depth for a single item type.

    Scope is repeated on each item so a summary remains meaningful when separated from
    its report. Monetary values are rounded to two decimal places. The depth metrics
    include every order at or better than `five_price`, including all orders tied at that
    price.
    """

    region_id: int
    type_id: int
    system_id: int | None
    location_id: int | None
    is_buy_summary: bool
    five_price: Decimal
    five_orders: int
    five_items: int
    lowest: Decimal
    highest: Decimal
    total_items: int
    total_orders: int
    average: Decimal
    filtered_items: int
    filtered_orders: int


@dataclass(slots=True, kw_only=True)
class BuySellSummary:
    """Represents the available buy and sell summaries for an item type."""

    buy_summary: OrderSummaryItem | None
    sell_summary: OrderSummaryItem | None

    @property
    def buy_5(self) -> Decimal | None:
        """Return the buy-side 5% depth price, if buy orders are available."""
        return self.buy_summary.five_price if self.buy_summary is not None else None

    @property
    def sell_5(self) -> Decimal | None:
        """Return the sell-side 5% depth price, if sell orders are available."""
        return self.sell_summary.five_price if self.sell_summary is not None else None


@dataclass(slots=True, kw_only=True)
class OrderSummaryReport(TimeStamped, Serializable):
    """Represents order summaries for a region and optional narrower scope.

    Calculation settings such as the outlier filter factor are input-only and are not
    persisted in the report.
    """

    region_id: int
    system_id: int | None
    location_id: int | None
    summaries: dict[int, BuySellSummary]

    def serialize(self, indent: int | None = 2) -> str:
        """Serialize the report to a JSON string."""
        return OrderSummaryReportRoot(root=self).model_dump_json(indent=indent)

    @classmethod
    def deserialize(cls, data: str) -> OrderSummaryReport:
        """Deserialize a JSON string to an order summary report."""
        return OrderSummaryReportRoot.model_validate_json(data).root

    def iter_summaries(self) -> Iterable[OrderSummaryItem]:
        """Iterate over all buy and sell summaries in the report."""
        for bs_summary in self.summaries.values():
            if bs_summary.buy_summary is not None:
                yield bs_summary.buy_summary
            if bs_summary.sell_summary is not None:
                yield bs_summary.sell_summary


OrderSummaryReportRoot = RootModel[OrderSummaryReport]


def calculate_summaries(
    region_orders: ARM.RegionMarketOrders,
    system_id: int | None = None,
    location_id: int | None = None,
    filter_factor: Decimal = Decimal("100.00"),
) -> OrderSummaryReport:
    """Summarize buy and sell depth for one region, or for a system/location subset.

    Each item summary is built from the filtered valid orders for that side of the book.
    The outlier filter removes extreme prices before the 5% depth threshold is computed.
    For buy orders, prices lower than the best price divided by `filter_factor` are
    discarded. For sell orders, prices higher than the best price multiplied by
    `filter_factor` are discarded. `filter_factor` must be greater than 1.0.

    Once the valid orders are selected, the algorithm calculates the price threshold at
    which 5% of the valid volume is available. This threshold is reported as
    `five_price` and the volume available at or better than that price is reported as
    `five_items`.

    Args:
        region_orders: The region-wide order payload to summarize.
        system_id: Optional solar system ID used to limit the summary to a single
            solar system. Cannot be combined with `location_id`.
        location_id: Optional location ID used to limit the summary to a single station or
            structure. Cannot be combined with `system_id`.
        filter_factor: Outlier-removal multiplier. Buy orders below
            `best_buy_price / filter_factor` are excluded, and sell orders above
            `best_sell_price * filter_factor` are excluded. Must be greater than 1.0.

    Returns:
        A report containing the buy and sell summaries for each item type. The input-only
        `filter_factor` is not stored in the report.

    Raises:
        ValueError: If both `system_id` and `location_id` are supplied, or if
            `filter_factor` is less than or equal to 1.0.
    """
    _validate_calculation_options(
        system_id=system_id,
        location_id=location_id,
        filter_factor=filter_factor,
    )
    summaries = OrderSummaryReport(
        received_at=region_orders.received_at,
        expires_at=region_orders.expires_at,
        region_id=region_orders.region_id,
        system_id=system_id,
        location_id=location_id,
        summaries={},
    )
    for type_id, divided_orders in region_orders.orders.items():
        summary = calculate_order_summary(
            region_id=region_orders.region_id,
            type_id=type_id,
            collected_orders=divided_orders,
            system_id=system_id,
            location_id=location_id,
            filter_factor=filter_factor,
        )
        summaries.summaries[type_id] = summary
    return summaries


def calculate_order_summary(
    region_id: int,
    type_id: int,
    collected_orders: ARM.DividedOrders,
    system_id: int | None = None,
    location_id: int | None = None,
    filter_factor: Decimal = Decimal("100.00"),
) -> BuySellSummary:
    """Summarize the buy and sell depth for one item type.

    The function first narrows the order set to the requested scope: whole region,
    specific solar system, or specific location. It then computes a buy-side and sell-side
    summary using the same outlier filter and 5% depth algorithm.

    Args:
        region_id: The region containing the orders.
        type_id: The item type being summarized.
        collected_orders: The buy and sell orders for the specified item type.
        system_id: Optional solar system filter. If provided, only orders from that
            solar system are included.
        location_id: Optional location filter. If provided, only orders from that location
            are included.
        filter_factor: Outlier-removal multiplier. Buy orders below
            `best_buy_price / filter_factor` are excluded, and sell orders above
            `best_sell_price * filter_factor` are excluded.

    Returns:
        The buy and sell summaries. A side is `None` when it has no scoped orders or
        its valid orders have no positive total volume.

    Raises:
        ValueError: If the scope is ambiguous, the filter factor is invalid, or an order
            has the wrong type or side.
    """
    _validate_calculation_options(
        system_id=system_id,
        location_id=location_id,
        filter_factor=filter_factor,
    )
    buy_orders = _orders_by_location(
        collected_orders.buy_orders,
        system_id=system_id,
        location_id=location_id,
    )
    sell_orders = _orders_by_location(
        collected_orders.sell_orders,
        system_id=system_id,
        location_id=location_id,
    )
    buy_summary = _calculate_buy_summary(
        region_id=region_id,
        type_id=type_id,
        system_id=system_id,
        location_id=location_id,
        orders=buy_orders,
        filter_factor=filter_factor,
    )
    sell_summary = _calculate_sell_summary(
        region_id=region_id,
        type_id=type_id,
        system_id=system_id,
        location_id=location_id,
        orders=sell_orders,
        filter_factor=filter_factor,
    )
    return BuySellSummary(
        buy_summary=buy_summary,
        sell_summary=sell_summary,
    )


def _validate_calculation_options(
    *,
    system_id: int | None,
    location_id: int | None,
    filter_factor: Decimal,
) -> None:
    if system_id is not None and location_id is not None:
        raise ValueError(
            "Cannot specify both system_id and location_id. Choose one or neither."
        )
    if filter_factor <= Decimal("1"):
        raise ValueError("filter_factor must be greater than 1.0.")


def _orders_by_location(
    orders: Sequence[ARM.MarketOrderDetail],
    system_id: int | None,
    location_id: int | None,
) -> list[ARM.MarketOrderDetail]:
    if system_id is None and location_id is None:
        return list(orders)
    if system_id is not None:
        return [order for order in orders if order.system_id == system_id]
    if location_id is not None:
        return [order for order in orders if order.location_id == location_id]
    return list(orders)


def _calculate_buy_summary(
    region_id: int,
    type_id: int,
    system_id: int | None,
    location_id: int | None,
    orders: Sequence[ARM.MarketOrderDetail],
    filter_factor: Decimal = Decimal("100.00"),
) -> OrderSummaryItem | None:
    """Summarize valid buy orders from highest price to lowest price."""
    _validate_orders(orders=orders, type_id=type_id, is_buy_summary=True)
    sorted_orders = sorted(orders, key=lambda order: order.price, reverse=True)
    if not sorted_orders:
        return None
    price_cutoff = sorted_orders[0].price / filter_factor
    valid_orders = [order for order in sorted_orders if order.price >= price_cutoff]
    excluded_orders = [order for order in sorted_orders if order.price < price_cutoff]
    return _build_order_summary(
        region_id=region_id,
        type_id=type_id,
        system_id=system_id,
        location_id=location_id,
        valid_orders=valid_orders,
        excluded_orders=excluded_orders,
        is_buy_summary=True,
        at_or_better=lambda price, threshold: price >= threshold,
    )


def _calculate_sell_summary(
    region_id: int,
    type_id: int,
    system_id: int | None,
    location_id: int | None,
    orders: Sequence[ARM.MarketOrderDetail],
    filter_factor: Decimal = Decimal("100.00"),
) -> OrderSummaryItem | None:
    """Summarize valid sell orders from lowest price to highest price."""
    _validate_orders(orders=orders, type_id=type_id, is_buy_summary=False)
    sorted_orders = sorted(orders, key=lambda order: order.price)
    if not sorted_orders:
        return None
    price_cutoff = sorted_orders[0].price * filter_factor
    valid_orders = [order for order in sorted_orders if order.price <= price_cutoff]
    excluded_orders = [order for order in sorted_orders if order.price > price_cutoff]
    return _build_order_summary(
        region_id=region_id,
        type_id=type_id,
        system_id=system_id,
        location_id=location_id,
        valid_orders=valid_orders,
        excluded_orders=excluded_orders,
        is_buy_summary=False,
        at_or_better=lambda price, threshold: price <= threshold,
    )


def _validate_orders(
    *,
    orders: Sequence[ARM.MarketOrderDetail],
    type_id: int,
    is_buy_summary: bool,
) -> None:
    for order in orders:
        if order.is_buy_order != is_buy_summary:
            msg = (
                f"Order is_buy_order {order.is_buy_order} does not match summary type "
                f"{is_buy_summary}"
            )
            raise ValueError(msg)
        if order.type_id != type_id:
            raise ValueError("All orders must be of the same type_id.")


def _build_order_summary(
    *,
    region_id: int,
    type_id: int,
    system_id: int | None,
    location_id: int | None,
    valid_orders: Sequence[ARM.MarketOrderDetail],
    excluded_orders: Sequence[ARM.MarketOrderDetail],
    is_buy_summary: bool,
    at_or_better: Callable[[Decimal, Decimal], bool],
) -> OrderSummaryItem | None:
    """Build aggregate metrics from best-price-ordered valid orders."""
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

    five_percent_orders = [
        order for order in valid_orders if at_or_better(order.price, five_price)
    ]
    avg_price = (
        sum(
            (order.volume_remain * order.price for order in valid_orders),
            start=Decimal(),
        )
        / total_items
    )
    return OrderSummaryItem(
        region_id=region_id,
        type_id=type_id,
        system_id=system_id,
        location_id=location_id,
        is_buy_summary=is_buy_summary,
        five_price=as_currency(five_price),
        five_orders=len(five_percent_orders),
        five_items=sum(order.volume_remain for order in five_percent_orders),
        lowest=as_currency(min(order.price for order in valid_orders)),
        highest=as_currency(max(order.price for order in valid_orders)),
        total_items=total_items,
        total_orders=len(valid_orders),
        average=as_currency(avg_price),
        filtered_items=sum(order.volume_remain for order in excluded_orders),
        filtered_orders=len(excluded_orders),
    )
