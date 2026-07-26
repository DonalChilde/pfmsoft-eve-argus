"""Market history summary calculation module.

This module provides functionality to calculate statistical summaries of market
history data over specified time periods, including volume-weighted price averages
and trading metrics.
"""

from datetime import date, timedelta

from esi_link.argus.calculations.models import HistorySummaryItem
from esi_link.argus.models.esi_models import (
    GetMarketsRegionIdHistory,
)


def date_range_days(start_date: str, days: int, descending: bool = True) -> list[str]:
    """Generate a list of date strings for a range of days.

    Args:
        start_date: The starting date as a string in 'YYYY-MM-DD' format.
        days: The number of days to include in the range.
        descending: If True, generates dates going backwards from the start_date.
                    If False, generates dates going forwards from the start_date.

    Returns:
        A list of date strings in 'YYYY-MM-DD' format.
    """
    start = date.fromisoformat(start_date)
    if descending:
        return [(start - timedelta(days=i)).isoformat() for i in range(days)]
    else:
        return [(start + timedelta(days=i)).isoformat() for i in range(days)]


def calculate_history_summary(
    history: GetMarketsRegionIdHistory,
    period: int,
    start_date: str | None = None,
) -> HistorySummaryItem:
    """Calculate a summary of market history data over a specified period.

    This function computes volume-weighted averages and other statistics for market
    history data over a given time period. It handles missing data points and
    calculates key metrics like price averages, order counts, and trading volumes.

    Args:
        history: The market history object containing daily trading
            data with region_id, type_id, and a dictionary of date-keyed market data.
        period: The number of days to include in the summary calculation,
            working backwards from the start_date.
        start_date: The starting date for the summary period.
            If None, uses the most recent date available in the history data.
            Defaults to None.

    Returns:
        A dictionary containing the following keys:
            - region_id: The region identifier from the input history
            - type_id: The item type identifier from the input history
            - period: The period length in days
            - start: The start date of the summary period
            - end: The end date of the summary period
            - missing: Count of dates with no data in the period
            - highest: Volume-weighted average of daily highest prices
            - average: Volume-weighted average of daily average prices
            - lowest: Volume-weighted average of daily lowest prices
            - order_count: Average daily order count across the period
            - volume: Average daily trading volume across the period

    Raises:
        ValueError: If the provided start_date is not present in the market history data.

    Notes:
        - Price averages (highest, average, lowest) are volume-weighted to give more
          importance to high-volume trading days
        - Order count and volume are simple averages across all days in the period
        - Days with missing data are counted but excluded from calculations
        - If total volume is zero, price averages default to 0.0
    """
    if start_date is None:
        start_date = history.most_recent_date
    if start_date not in history.history:
        raise ValueError(f"Start date {start_date} not in market history data")
    dates = list(date_range_days(start_date=start_date, days=period, descending=True))
    missing = order_count = 0
    average = highest = lowest = volume = 0.0
    for date_key in dates:
        item = history.history.get(date_key, None)
        if item is None:
            missing += 1
            continue
        average = average + (item.average * item.volume)
        highest = highest + (item.highest * item.volume)
        lowest = lowest + (item.lowest * item.volume)
        order_count = order_count + item.order_count
        volume = volume + item.volume
    summary: HistorySummaryItem = HistorySummaryItem(
        region_id=history.region_id,
        type_id=history.type_id,
        period=period,
        start=start_date,
        end=dates[-1],
        missing=missing,
        highest=highest / volume if volume > 0 else 0.0,
        average=average / volume if volume > 0 else 0.0,
        lowest=lowest / volume if volume > 0 else 0.0,
        order_count=int(order_count / len(dates)) if len(dates) > 0 else 0,
        volume=volume / len(dates) if len(dates) > 0 else 0.0,
    )
    return summary
