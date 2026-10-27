"""Shared CLI inputs for reports that use every configured market hub's orders."""

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

import typer

from pfmsoft.eve_argus.dynamic import read as dynamic_read
from pfmsoft.eve_argus.dynamic.models import MarketOrdersResponse
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS, MarketHub


@dataclass(slots=True, kw_only=True, frozen=True)
class HubSnapshot:
    """The latest regional order response selected for one hub."""

    hub: MarketHub
    response: MarketOrdersResponse


def percent_option(help_text: str) -> typer.models.OptionInfo:
    """Build a 0-100 percent option."""
    return typer.Option(min=0, max=100, help=help_text)


def option_decimal(value: float) -> Decimal:
    """Convert a CLI float without binary-float artifacts or a trailing `.0`."""
    return Decimal(int(value)) if value.is_integer() else Decimal(str(value))


def select_hub_snapshots(dynamic: sqlite3.Connection) -> list[HubSnapshot]:
    """Select the latest regional order response for every hub.

    Raises:
        ValueError: If any hub has no stored orders.
    """
    responses_by_region = {
        region_id: dynamic_read.market_orders_responses(dynamic, region_id=region_id)
        for region_id in dict.fromkeys(hub.region_id for hub in MARKET_HUBS)
    }
    missing = [
        hub.system_name for hub in MARKET_HUBS if not responses_by_region[hub.region_id]
    ]
    if missing:
        raise ValueError(
            f"No stored regional market orders for: {', '.join(missing)}. "
            "Run 'eve-argus fetch market-orders --hubs' to fetch source orders."
        )
    return [
        HubSnapshot(hub=hub, response=responses_by_region[hub.region_id][0])
        for hub in MARKET_HUBS
    ]
