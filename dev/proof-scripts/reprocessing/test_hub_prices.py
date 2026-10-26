"""Regression tests for on-demand prices in the reprocessing proof."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from runpy import run_path
from unittest.mock import Mock

import pytest

from pfmsoft.eve_argus.dynamic import read, util
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS

load_hub_prices = run_path(str(Path(__file__).with_name("generate_value_report.py")))[
    "load_hub_prices"
]
HUB = MARKET_HUBS[0]


@pytest.fixture
def connection() -> Iterator[sqlite3.Connection]:
    """Provide raw regional snapshots without any saved summaries."""
    with closing(sqlite3.connect(":memory:")) as database:
        database.executescript(util.load_table_definitions())
        for source_id, received_at in (
            (1, "2026-10-24T00:00:00Z"),
            (2, "2026-10-25T00:00:00Z"),
        ):
            database.execute(
                "INSERT INTO response_metadata (id, received_at) VALUES (?, ?)",
                (source_id, received_at),
            )
            database.execute(
                """INSERT INTO get_markets_region_id_orders_response
                   (response_metadata_id, region_id, received_at) VALUES (?, ?, ?)""",
                (source_id, HUB.region_id, received_at),
            )
        for order_id, (source_id, is_buy, cents, volume, system_id) in enumerate(
            (
                (1, True, 99900, 10, HUB.system_id),
                (2, True, 1000, 10, HUB.system_id),
                (2, True, 1000, 20, HUB.system_id),
                (2, True, 1000, 30, HUB.system_id),
                (2, False, 1200, 10, HUB.system_id),
                (2, False, 130000, 100, HUB.system_id),
                (2, True, 88800, 10, HUB.system_id + 1),
            ),
            start=1,
        ):
            database.execute(
                """INSERT INTO market_orders
                   (response_metadata_id, region_id, duration, is_buy_order, issued,
                    location_id, min_volume, order_id, price, range_, system_id,
                    type_id, volume_remain, volume_total)
                   VALUES (?, ?, 90, ?, '2026-10-25T00:00:00Z', ?, 1, ?, ?,
                           'station', ?, 34, ?, ?)""",
                (
                    source_id,
                    HUB.region_id,
                    is_buy,
                    HUB.station_id + order_id,
                    order_id,
                    cents,
                    system_id,
                    volume,
                    volume,
                ),
            )
        yield database


def test_prices_calculated_from_latest_regional_orders(
    connection: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Load a whole snapshot once, scope to the system, and retain depth metrics."""
    orders = Mock(wraps=read.market_orders)
    monkeypatch.setattr(read, "market_orders", orders)
    for name in (
        "order_summary_responses",
        "order_summaries",
        "calculate_market_order_summary",
        "market_orders_filtered",
    ):
        monkeypatch.setattr(
            read, name, Mock(side_effect=AssertionError(f"Unexpected query: {name}"))
        )

    prices, received_at = load_hub_prices(connection, HUB)

    assert received_at == "2026-10-25T00:00:00Z"
    assert prices == {
        34: {
            "buy": {
                "price": Decimal("10.00"),
                "orders": 3,
                "items": 60,
                "status": "complete",
            },
            "sell": {
                "price": Decimal("12.00"),
                "orders": 1,
                "items": 10,
                "status": "thin",
            },
        }
    }
    orders.assert_called_once_with(connection, response_metadata_id=2)


@pytest.mark.parametrize("outside_system", [False, True])
def test_latest_without_hub_orders_does_not_fall_back(
    connection: sqlite3.Connection, *, outside_system: bool
) -> None:
    """An empty latest snapshot or hub scope must not reuse older prices."""
    if outside_system:
        connection.execute(
            "UPDATE market_orders SET system_id = ? WHERE response_metadata_id = 2",
            (HUB.system_id + 1,),
        )
    else:
        connection.execute("DELETE FROM market_orders WHERE response_metadata_id = 2")

    assert load_hub_prices(connection, HUB) == ({}, "2026-10-25T00:00:00Z")


def test_missing_regional_snapshot_is_explicit(connection: sqlite3.Connection) -> None:
    """Explain how to fetch missing source orders instead of returning empty prices."""
    with pytest.raises(ValueError, match="fetch market-orders --hubs"):
        load_hub_prices(connection, MARKET_HUBS[1])
