"""Helper functions for market history calculations."""

from pfmsoft.eve_snippets.eve.eve_dates import downtime_bracket
from whenever import Instant


def first_possible_date(received_at: str) -> str:
    """Return the first possible date for market history based on the received_at date.

    The first possible date is determined based on the downtime bracket of the
    received_at date, which is the date that the request for market history was made.

    Market history is updated at downtime, which happens at 11:00 UTC.

    Args:
        received_at (str): The date and time when the market history was received.

    Returns:
        str: The first possible date for market history in ISO format (YYYY-MM-DD).

    Example:
        >>> first_possible_date("2024-06-15T12:34:56Z")
        '2024-06-14'
    """
    instant = Instant(received_at)
    previous_dt, _next_dt = downtime_bracket(instant)
    return previous_dt.to_stdlib().date().isoformat()
