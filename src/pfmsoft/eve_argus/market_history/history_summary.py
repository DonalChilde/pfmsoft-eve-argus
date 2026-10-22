"""Calculate market-history summaries from stored market-history records."""

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal

from pfmsoft.eve_argus.market_history.models import (
    HistorySummaryRecord,
    MarketHistoryRecord,
)


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
        - If the total valid volume is zero, all weighted price fields are reported as 0.
        - Records with dates outside `dates` are ignored.
        - `start` is the newest requested date and `end` is the oldest, regardless of
          the order of `dates`.
        - Response metadata (received/expiry timestamps) is taken from the most
          recently received record.
    """
    if not dates:
        raise ValueError("The dates sequence is empty; cannot calculate summary.")
    if not records:
        raise ValueError("Market history records are empty; cannot calculate summary.")
    region_ids = {record.region_id for record in records}
    if len(region_ids) > 1:
        raise ValueError(f"Records contain multiple region_id values: {region_ids}")
    type_ids = {record.type_id for record in records}
    if len(type_ids) > 1:
        raise ValueError(f"Records contain multiple type_id values: {type_ids}")
    indexed_records = {record.date: record for record in records}
    missing = order_count = volume = 0
    average = highest = lowest = Decimal(0)
    for date_key in dates:
        record = indexed_records.get(date_key)
        if record is None:
            missing += 1
            continue
        average += record.average * record.volume
        highest += record.highest * record.volume
        lowest += record.lowest * record.volume
        order_count += record.order_count
        volume += record.volume
    metadata = max(records, key=lambda record: record.received_at)
    return HistorySummaryRecord(
        received_at=metadata.received_at,
        expires_at=metadata.expires_at,
        argus_expires_at=metadata.argus_expires_at,
        region_id=metadata.region_id,
        type_id=metadata.type_id,
        start=max(dates),
        end=min(dates),
        missing=missing,
        highest=highest / volume if volume > 0 else Decimal(0),
        average=average / volume if volume > 0 else Decimal(0),
        lowest=lowest / volume if volume > 0 else Decimal(0),
        order_count=order_count // len(dates),
        volume=Decimal(volume) / len(dates),
    )
