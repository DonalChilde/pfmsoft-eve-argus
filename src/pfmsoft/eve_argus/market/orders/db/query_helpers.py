"""Query helpers for the market orders database."""

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from pfmsoft.eve_argus.helpers.currency import from_cents, to_cents
from pfmsoft.eve_argus.helpers.package_resource import load_package_resouce_text
from pfmsoft.eve_argus.models.esi import argus_response_models as ARM
from pfmsoft.eve_argus.models.esi import esi_response_models as ERM
from pfmsoft.eve_argus.models.esi.argus_response_models import RegionMarketOrders

_table_def_parent = "pfmsoft.eve_argus.market.orders.db"
_table_def_file = "table_definitions.sql"


def load_table_definitions() -> str:
    """Load the SQL table definitions for the market orders database."""
    return load_package_resouce_text(_table_def_parent, _table_def_file)


@dataclass(slots=True, kw_only=True)
class OrderResponse:
    region_id: int
    received_at: str
    expires_at: str


@dataclass(slots=True, kw_only=True)
class OrderCountBySystem:
    system_id: int
    buy_orders: int
    sell_orders: int


def write_market_orders(
    connection: sqlite3.Connection,
    market_orders: ERM.GetMarketsRegionIdOrders,
) -> None:
    """Write market orders to the database."""
    delete_order_response(connection, market_orders.region_id)
    with connection:
        connection.execute(
            """
                INSERT INTO order_response (region_id, received_at, expires_at)
                VALUES (?, ?, ?)
                """,
            (
                market_orders.region_id,
                market_orders.received_at,
                market_orders.expires_at,
            ),
        )
        # Write the market orders to the database, associating them with the order response.
        connection.executemany(
            """
            INSERT INTO market_orders (
                region_id, duration, is_buy_order, issued, location_id,
                min_volume, order_id, price, range_, system_id, type_id,
                volume_remain, volume_total
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    market_orders.region_id,
                    order.duration,
                    order.is_buy_order,
                    order.issued,
                    order.location_id,
                    order.min_volume,
                    order.order_id,
                    to_cents(Decimal(order.price)),
                    order.range,
                    order.system_id,
                    order.type_id,
                    order.volume_remain,
                    order.volume_total,
                )
                for order in market_orders.orders
            ),
        )


def delete_order_response(connection: sqlite3.Connection, region_id: int) -> None:
    """Delete the order response and its associated market orders from the database, including both buy and sell orders."""
    with connection:
        connection.execute(
            "DELETE FROM market_orders WHERE region_id = ?",
            (region_id,),
        )
        connection.execute(
            "DELETE FROM order_response WHERE region_id = ?",
            (region_id,),
        )


def get_region_orders(
    connection: sqlite3.Connection,
    region_id: int,
    type_id: int | None = None,
    is_buy_order: bool | None = None,
    system_id: int | None = None,
    location_id: int | None = None,
) -> list[ARM.MarketOrderDetail]:
    """Retrieve market orders for a specific region with optional filters."""
    query = """
        SELECT duration, is_buy_order, issued, location_id, min_volume,
            order_id, price, range_, system_id, type_id,
            volume_remain, volume_total
        FROM market_orders
        WHERE region_id = ?
    """
    params = [region_id]
    if type_id is not None:
        query += " AND type_id = ?"
        params.append(type_id)
    if is_buy_order is not None:
        query += " AND is_buy_order = ?"
        params.append(is_buy_order)
    if system_id is not None:
        query += " AND system_id = ?"
        params.append(system_id)
    if location_id is not None:
        query += " AND location_id = ?"
        params.append(location_id)

    with connection:
        cursor = connection.execute(query, tuple(params))
        orders = [
            ARM.MarketOrderDetail(
                duration=row[0],
                is_buy_order=row[1],
                issued=row[2],
                location_id=row[3],
                min_volume=row[4],
                order_id=row[5],
                price=from_cents(row[6]),
                range=row[7],
                system_id=row[8],
                type_id=row[9],
                volume_remain=row[10],
                volume_total=row[11],
            )
            for row in cursor
        ]
    return orders


def get_order_count_by_system(
    connection: sqlite3.Connection, region_id: int
) -> tuple[int, list[OrderCountBySystem]]:
    """Retrieve the count of market orders grouped by system for a specific region."""
    query = """
        SELECT system_id,
            SUM(CASE WHEN is_buy_order = 1 THEN 1 ELSE 0 END) as buy_orders,
            SUM(CASE WHEN is_buy_order = 0 THEN 1 ELSE 0 END) as sell_orders
        FROM market_orders
        WHERE region_id = ?
        GROUP BY system_id
    """
    with connection:
        cursor = connection.execute(query, (region_id,))
        results = [
            OrderCountBySystem(
                system_id=row[0],
                buy_orders=row[1],
                sell_orders=row[2],
            )
            for row in cursor
        ]
    total_count = sum(item.buy_orders + item.sell_orders for item in results)
    return total_count, results


def get_region_market_orders(
    connection: sqlite3.Connection, order_response: OrderResponse
) -> RegionMarketOrders:
    """Retrieve the market orders associated with a given order response ID."""
    with connection:
        cursor = connection.execute(
            """
            SELECT duration, is_buy_order, issued, location_id, min_volume,
                order_id, price, range_, system_id, type_id, volume_remain,
                volume_total
            FROM market_orders
            WHERE region_id = ?
            """,
            (order_response.region_id,),
        )
        orders_by_type: dict[int, ARM.DividedOrders] = {}
        for row in cursor:
            order = ARM.MarketOrderDetail(
                duration=row[0],
                is_buy_order=row[1],
                issued=row[2],
                location_id=row[3],
                min_volume=row[4],
                order_id=row[5],
                price=Decimal(row[6]) / 100,
                range=row[7],
                system_id=row[8],
                type_id=row[9],
                volume_remain=row[10],
                volume_total=row[11],
            )
            type_orders = orders_by_type.setdefault(order.type_id, ARM.DividedOrders())
            if order.is_buy_order:
                type_orders.buy_orders.append(order)
            else:
                type_orders.sell_orders.append(order)

    return RegionMarketOrders(
        region_id=order_response.region_id,
        received_at=order_response.received_at,
        expires_at=order_response.expires_at,
        orders=orders_by_type,
    )


def get_order_responses(connection: sqlite3.Connection) -> list[OrderResponse]:
    """Retrieve all order responses from the database."""
    with connection:
        cursor = connection.cursor()
        order_responses = cursor.execute("SELECT * FROM order_response").fetchall()
    return order_responses


def get_order_response(connection: sqlite3.Connection, region_id: int) -> OrderResponse:
    """Retrieve the order response for a specific region from the database."""
    with connection:
        cursor = connection.execute(
            "SELECT * FROM order_response WHERE region_id = ?",
            (region_id,),
        )
        order_response = cursor.fetchone()
    if order_response is None:
        raise ValueError(f"No order response found for region {region_id}")
    return order_response
