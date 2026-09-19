"""Query helpers for the market orders database."""

import sqlite3
from decimal import Decimal
from typing import TypedDict

from pfmsoft.eve_argus.helpers.package_resource import load_package_resouce_text
from pfmsoft.eve_argus.models.esi import argus_response_models as ARM
from pfmsoft.eve_argus.models.esi import esi_response_models as ERM
from pfmsoft.eve_argus.models.esi.argus_response_models import RegionMarketOrders

_table_def_parent = "pfmsoft.eve_argus.market.orders.db"
_table_def_file = "table_definitions.sql"


def load_table_definitions() -> str:
    """Load the SQL table definitions for the market orders database."""
    return load_package_resouce_text(_table_def_parent, _table_def_file)


class OrderResponse(TypedDict):
    region_id: int
    received_at: str
    expires_at: str


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
                    int(order.price * 100),
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


def get_region_market_orders(
    connection: sqlite3.Connection, order_response: OrderResponse
) -> RegionMarketOrders:
    """Retrieve the market orders associated with a given order response ID."""
    with connection:
        cursor = connection.execute(
            "SELECT * FROM market_orders WHERE region_id = ?",
            (order_response["region_id"],),
        )
        # orders = cursor.fetchall()
        order_details = [
            ARM.MarketOrderDetail(
                duration=row["duration"],
                is_buy_order=row["is_buy_order"],
                issued=row["issued"],
                location_id=row["location_id"],
                min_volume=row["min_volume"],
                order_id=row["order_id"],
                price=Decimal(row["price"]) / 100,
                range=row["range_"],
                system_id=row["system_id"],
                type_id=row["type_id"],
                volume_remain=row["volume_remain"],
                volume_total=row["volume_total"],
            )
            for row in cursor.fetchall()
        ]
        orders_by_type: dict[int, ARM.DividedOrders] = {}
        for order in order_details:
            type_orders = orders_by_type.setdefault(order.type_id, ARM.DividedOrders())
            if order.is_buy_order:
                type_orders.buy_orders.append(order)
            else:
                type_orders.sell_orders.append(order)

    return RegionMarketOrders(
        region_id=order_response["region_id"],
        received_at=order_response["received_at"],
        expires_at=order_response["expires_at"],
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
