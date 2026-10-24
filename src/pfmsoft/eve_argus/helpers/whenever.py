"""Helper functions for generating date ranges."""

from collections.abc import Iterator

from whenever import Date


def date_range(start: Date, end: Date) -> Iterator[Date]:
    """Generate a range of dates from start to end, inclusive.

    Args:
        start: The starting date of the range.
        end: The ending date of the range.

    Yields:
        Dates from start to end, inclusive.
    """
    current = start
    if start <= end:
        while current <= end:
            yield current
            current = current.next_day()
    else:
        while current >= end:
            yield current
            current = current.prev_day()


def date_range_iso(start: str, end: str) -> Iterator[str]:
    """Generate a range of ISO date strings from start to end, inclusive.

    Args:
        start: The starting ISO date string of the range.
        end: The ending ISO date string of the range.

    Yields:
        ISO date strings from start to end, inclusive.
    """
    start_date = Date.parse_iso(start)
    end_date = Date.parse_iso(end)
    for date in date_range(start_date, end_date):
        yield date.format_iso()


def date_range_days(start: Date, days: int, future: bool = True) -> Iterator[Date]:
    """Generate a range of dates starting from start for a given number of days.

    Args:
        start: The starting date of the range.
        days: The number of days to generate.
        future: If True, generate future dates; if False, generate past dates.

    Yields:
        Dates from start for the specified number of days.
    """
    if days <= 0:
        return
    current = start
    for _ in range(days):
        yield current
        current = current.next_day() if future else current.prev_day()
