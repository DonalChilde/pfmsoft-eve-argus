"""Module for calculating market history summaries."""

from datetime import date, timedelta

from pfmsoft.eve_argus.models.esi import esi_argus, esi_response
from pfmsoft.eve_argus.models.types import RegionID, TypeID


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
    history: esi_response.GetMarketsRegionIdHistory,
    period: int,
    start_date: str | None = None,
) -> esi_argus.HistorySummary:
    """Calculate a volume-weighted summary for a market history window.

    The summary covers `period` consecutive days ending on `start_date`. If
    `start_date` is omitted, the newest available date in the provided history is used.
    Missing dates are counted in `missing`, but they are excluded from the weighted price
    calculations and contribute zero to the daily average totals.

    The price fields are each computed as a volume-weighted average over the selected dates:
    `highest` is the weighted mean of the daily highest prices, `average` is the weighted
    mean of the daily average prices, and `lowest` is the weighted mean of the daily
    lowest prices. `order_count` is the average daily order count across the full window,
    and `volume` is the average daily traded volume across the same window.

    Args:
        history: The full market history payload containing daily trading data for one
            region and item type.
        period: The number of consecutive days to include in the summary.
        start_date: The end date of the summary window as an ISO date string in
            `YYYY-MM-DD` format. If omitted, the newest date in the history payload is
            used.

    Returns:
        A `HistorySummaryItem` containing the aggregated price and volume metrics for the
        selected period.

    Raises:
        ValueError: If `period` is not positive, if the history payload is empty, or if
            `start_date` is not present in the supplied history data.

    Notes:
        - The per-day price values are weighted by that day's traded volume.
        - `missing` counts dates in the requested window that are absent from the history.
        - If the total valid volume is zero, all weighted price fields are reported as 0.0.
    """
    if period <= 0:
        raise ValueError("Period must be a positive integer.")
    # Sort the history entries by date in descending order to ensure we process the most
    # recent data first
    history_entries: list[esi_response.GetMarketsRegionIdHistoryDetail] = sorted(
        history.history, key=lambda x: x.date, reverse=True
    )
    if not history_entries:
        raise ValueError("Market history data is empty; cannot calculate summary.")
    if start_date is None:
        start_date = history_entries[0].date
    else:
        if start_date not in [entry.date for entry in history_entries]:
            raise ValueError(f"Start date {start_date} not in market history data")
    dates = list(date_range_days(start_date=start_date, days=period, descending=True))
    history_dict: dict[str, esi_response.GetMarketsRegionIdHistoryDetail] = {
        entry.date: entry for entry in history_entries
    }
    missing = order_count = 0
    average = highest = lowest = volume = 0.0
    for date_key in dates:
        item = history_dict.get(date_key, None)
        if item is None:
            missing += 1
            continue
        average = average + (item.average * item.volume)
        highest = highest + (item.highest * item.volume)
        lowest = lowest + (item.lowest * item.volume)
        order_count = order_count + item.order_count
        volume = volume + item.volume
    summary = esi_argus.HistorySummary(
        received_at=history.received_at,
        expires_at=history.expires_at,
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


RegionalHistories = dict[RegionID, dict[TypeID, esi_response.GetMarketsRegionIdHistory]]


def calculate_regional_history_summaries(
    regional_histories: RegionalHistories,
    period: int,
) -> esi_argus.RegionalHistorySummaries:
    """Calculate history summaries for all item types in a region.

    Args:
        regional_histories: The ESI response containing market history data for multiple
            item types in a region.
        period: The number of consecutive days to include in each summary.

    Returns:
        A `RegionalHistorySummaries` object containing the aggregated summaries for all
        item types in the region.
    """
    if not regional_histories:
        raise ValueError(
            "Regional histories data is empty; cannot calculate summaries."
        )
    if len(regional_histories) > 1:
        raise ValueError(
            "Regional histories data contains multiple regions; expected only one region."
        )
    region_id = next(iter(regional_histories.keys()))
    summaries: dict[TypeID, esi_argus.HistorySummary] = {}
    for type_id, history in regional_histories[region_id].items():
        summary = calculate_history_summary(history=history, period=period)
        summaries[type_id] = summary
    return esi_argus.RegionalHistorySummaries(region_id=region_id, summaries=summaries)
