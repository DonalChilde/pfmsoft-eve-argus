"""Tests for dynamic database market-order summaries."""

from decimal import Decimal

import pytest

from pfmsoft.eve_argus.dynamic.db import models, order_summary


def _order(
    order_id: int,
    *,
    price: str,
    volume: int,
    is_buy_order: bool,
    type_id: int = 34,
    system_id: int = 30000142,
    location_id: int = 60003760,
) -> models.MarketOrderRecord:
    return models.MarketOrderRecord(
        response_metadata_id=17,
        region_id=10000002,
        duration=90,
        is_buy_order=is_buy_order,
        issued="2026-09-01T00:00:00Z",
        location_id=location_id,
        min_volume=1,
        order_id=order_id,
        price=Decimal(price),
        range="station",
        system_id=system_id,
        type_id=type_id,
        volume_remain=volume,
        volume_total=volume,
    )


def _dataset(
    records: dict[int, models.BuySellOrders],
) -> models.MarketOrdersDataset:
    return models.MarketOrdersDataset(
        response_metadata_id=17,
        received_at="2026-09-01T00:00:00Z",
        expires_at="2026-09-02T00:00:00Z",
        argus_expires_at="2026-09-01T12:00:00Z",
        region_id=10000002,
        records=records,
    )


def test_calculate_summaries_builds_dataset_from_market_orders() -> None:
    """The dataset owns the source response ID and timestamps."""
    orders = _dataset(
        {
            34: models.BuySellOrders(
                buy_orders=(
                    _order(1, price="100", volume=10, is_buy_order=True),
                    _order(2, price="90", volume=20, is_buy_order=True),
                    _order(3, price="5", volume=30, is_buy_order=True),
                ),
                sell_orders=(
                    _order(4, price="110", volume=10, is_buy_order=False),
                    _order(5, price="120", volume=20, is_buy_order=False),
                    _order(6, price="1200", volume=30, is_buy_order=False),
                ),
            )
        }
    )

    result = order_summary.calculate_summaries(orders, filter_factor=Decimal("10"))

    assert isinstance(result, models.OrderSummaryDataset)
    assert (result.response_metadata_id, result.received_at) == (17, orders.received_at)
    assert (result.expires_at, result.argus_expires_at) == (
        orders.expires_at,
        orders.argus_expires_at,
    )
    assert (result.region_id, result.system_id, result.location_id) == (
        10000002,
        None,
        None,
    )
    assert set(result.records) == {34}
    buy = result.records[34].buy_summary
    sell = result.records[34].sell_summary
    assert isinstance(buy, models.OrderSummaryRecord)
    assert isinstance(sell, models.OrderSummaryRecord)
    assert not hasattr(buy, "response_metadata_id")
    assert not hasattr(sell, "response_metadata_id")
    assert (buy.five_price, buy.five_orders, buy.five_items) == (
        Decimal("100.00"),
        1,
        10,
    )
    assert (buy.total_items, buy.total_orders, buy.average) == (
        30,
        2,
        Decimal("93.33"),
    )
    assert (buy.filtered_items, buy.filtered_orders) == (30, 1)
    assert (sell.five_price, sell.average, sell.filtered_orders) == (
        Decimal("110.00"),
        Decimal("116.67"),
        1,
    )


@pytest.mark.parametrize(
    ("scope", "scope_id"),
    [("system_id", 30000142), ("location_id", 60003760)],
)
def test_calculate_summaries_scopes_orders_and_includes_price_ties(
    scope: str, scope_id: int
) -> None:
    """The threshold counts all tied orders within the requested scope."""
    orders = _dataset(
        {
            34: models.BuySellOrders(
                buy_orders=(
                    _order(1, price="100", volume=5, is_buy_order=True),
                    _order(2, price="100", volume=5, is_buy_order=True),
                    _order(3, price="99", volume=100, is_buy_order=True),
                    _order(
                        4,
                        price="1000",
                        volume=50,
                        is_buy_order=True,
                        system_id=30000143,
                        location_id=60003761,
                    ),
                ),
                sell_orders=(
                    _order(5, price="100", volume=5, is_buy_order=False),
                    _order(6, price="100", volume=5, is_buy_order=False),
                    _order(7, price="101", volume=100, is_buy_order=False),
                    _order(
                        8,
                        price="1",
                        volume=50,
                        is_buy_order=False,
                        system_id=30000143,
                        location_id=60003761,
                    ),
                ),
            )
        }
    )
    original_buy_orders = orders.records[34].buy_orders

    result = order_summary.calculate_summaries(orders, **{scope: scope_id})

    assert (result.system_id, result.location_id) == (
        scope_id if scope == "system_id" else None,
        scope_id if scope == "location_id" else None,
    )
    assert orders.records[34].buy_orders == original_buy_orders
    for summary in result.iter_summaries():
        assert isinstance(summary, models.OrderSummaryRecord)
        assert (summary.system_id, summary.location_id) == (
            result.system_id,
            result.location_id,
        )
        assert (summary.five_price, summary.five_orders, summary.five_items) == (
            Decimal("100.00"),
            2,
            10,
        )
        assert summary.total_items == 110


def test_calculate_summaries_reaches_exact_five_percent_and_sorts_orders() -> None:
    """The best order sets the threshold when it reaches exactly 5% of volume."""
    orders = _dataset(
        {
            34: models.BuySellOrders(
                buy_orders=(
                    _order(1, price="90", volume=95, is_buy_order=True),
                    _order(2, price="100", volume=5, is_buy_order=True),
                ),
                sell_orders=(),
            )
        }
    )

    result = order_summary.calculate_summaries(orders)

    assert result.records[34].buy_summary is not None
    assert result.records[34].buy_summary.five_price == Decimal("100.00")
    assert result.records[34].buy_summary.five_items == 5
    assert result.records[34].buy_summary.average == Decimal("90.50")
    assert result.records[34].sell_summary is None


def test_calculate_summaries_handles_empty_and_nonpositive_books() -> None:
    """Keep type keys, even when neither side produces a summary."""
    empty = order_summary.calculate_summaries(_dataset({}))
    assert empty.records == {}

    orders = _dataset(
        {
            34: models.BuySellOrders(
                buy_orders=(_order(1, price="100", volume=0, is_buy_order=True),),
                sell_orders=(),
            ),
            35: models.BuySellOrders(
                buy_orders=(),
                sell_orders=(
                    _order(2, price="110", volume=1, is_buy_order=False, type_id=35),
                ),
            ),
        }
    )

    result = order_summary.calculate_summaries(orders)

    assert set(result.records) == {34, 35}
    assert result.records[34] == models.BuySellSummary(
        buy_summary=None, sell_summary=None
    )
    assert result.records[35].buy_summary is None
    assert result.records[35].sell_summary is not None
    assert result.records[35].sell_summary.type_id == 35
    assert list(result.iter_summaries()) == [result.records[35].sell_summary]
    assert order_summary.calculate_summaries(orders, system_id=30000143).records == {
        34: models.BuySellSummary(buy_summary=None, sell_summary=None),
        35: models.BuySellSummary(buy_summary=None, sell_summary=None),
    }


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"system_id": 30000142, "location_id": 60003760}, "both"),
        ({"filter_factor": Decimal("1")}, "greater than 1"),
        ({"filter_factor": Decimal("0")}, "greater than 1"),
    ],
)
def test_calculate_summaries_rejects_invalid_options(
    options: dict[str, int | Decimal], message: str
) -> None:
    """Invalid calculation options fail even for an empty book."""
    with pytest.raises(ValueError, match=message):
        order_summary.calculate_summaries(_dataset({}), **options)


@pytest.mark.parametrize(
    ("bad_order", "message"),
    [
        (_order(1, price="100", volume=1, is_buy_order=False), "does not match"),
        (_order(2, price="100", volume=1, is_buy_order=True, type_id=35), "type_id"),
    ],
)
def test_calculate_summaries_rejects_invalid_orders(
    bad_order: models.MarketOrderRecord, message: str
) -> None:
    """Order type and side must match the enclosing type and book side."""
    orders = _dataset(
        {34: models.BuySellOrders(buy_orders=(bad_order,), sell_orders=())}
    )

    with pytest.raises(ValueError, match=message):
        order_summary.calculate_summaries(orders)
