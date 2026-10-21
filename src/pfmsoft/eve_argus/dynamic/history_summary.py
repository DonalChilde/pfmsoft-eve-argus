from collections.abc import Sequence
from datetime import date, timedelta

from pfmsoft.eve_argus.dynamic.models import HistorySummaryRecord
from pfmsoft.eve_argus.market_history.models import MarketHistoryRecord


def date_range_days(start_date: str, days: int, descending: bool = True) -> list[str]:
    """Generate a consecutive set of ISO date strings.

    The function requires a positive `days` value. When `descending` is True, the list is
    generated in reverse chronological order from `start_date` back to
    `start_date - (days - 1) days`. When `descending` is False, it moves forward from
    `start_date` to `start_date + (days - 1) days`.

    Args:
        start_date: The start date as an ISO string in `YYYY-MM-DD` format.
        days: The number of consecutive days to include. Must be at least 1.
        descending: If True, generate dates backwards from `start_date`; otherwise,
            generate dates forwards from `start_date`.

    Example:
        date_range_days("2024-06-01", 3, descending=True)
        # Returns ["2024-06-01", "2024-05-31", "2024-05-30"]

    Returns:
        A list of ISO date strings in the requested order.

    Raises:
        ValueError: If `days` is less than or equal to 0.
    """
    if days <= 0:
        raise ValueError("Days must be a positive integer.")
    start = date.fromisoformat(start_date)
    if descending:
        return [(start - timedelta(days=i)).isoformat() for i in range(days)]
    else:
        return [(start + timedelta(days=i)).isoformat() for i in range(days)]


def calculate_history_summary(
    records: tuple[MarketHistoryRecord, ...], dates: Sequence[str]
) -> HistorySummaryRecord:
    """Calculate a volume-weighted summary for a market history window.

    The summary covers dates specified in the `dates` sequence.
    Missing dates are counted in `missing`, but they are excluded from the weighted price
    calculations and contribute zero to the daily average totals.

    The price fields are each computed as a volume-weighted average over the selected dates:
    `highest` is the weighted mean of the daily highest prices, `average` is the weighted
    mean of the daily average prices, and `lowest` is the weighted mean of the daily
    lowest prices. `order_count` is the average daily order count across the full window,
    and `volume` is the average daily traded volume across the same window.

    Args:
        records: The full market history payload containing daily trading data for one
            region and item type.
        dates: A sequence of ISO date strings specifying the dates to include in the summary.

    Returns:
        A HistorySummaryRecord containing the aggregated price and volume metrics for the
        specified dates.

    Raises:
        ValueError: If `dates` is empty, if the history payload is empty, or region_id
            or type_id are inconsistent across the records.

    Notes:
        - The per-day price values are weighted by that day's traded volume.
        - `missing` counts dates in the requested window that are absent from the history.
        - If the total valid volume is zero, all weighted price fields are reported as 0.0.
    """
    ...
