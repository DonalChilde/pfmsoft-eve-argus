"""Market history models."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(slots=True, kw_only=True, frozen=True)
class MarketHistoryResponse:
    response_metadata_id: int
    received_at: str
    expires_at: str | None
    argus_expires_at: str | None
    region_id: int
    type_id: int
    response_count: int


@dataclass(slots=True, kw_only=True, frozen=True)
class MarketHistoryRecord:
    received_at: str
    expires_at: str | None
    argus_expires_at: str | None
    region_id: int
    type_id: int
    average: Decimal
    date: str
    highest: Decimal
    lowest: Decimal
    order_count: int
    volume: int


@dataclass(slots=True, kw_only=True, frozen=True)
class HistorySummaryRecord:
    """Represents an aggregate market-history summary for one region and item type.

    The summary covers a fixed window of consecutive days and stores the volume-weighted
    price averages for that window along with the average daily order count and volume.
    """

    received_at: str
    """The timestamp when this summary was received."""
    expires_at: str | None
    """The timestamp when this summary expires, if known."""
    argus_expires_at: str | None
    """The timestamp when this summary is considered expired by Argus, if known."""
    region_id: int
    """The region ID associated with this summary."""
    type_id: int
    """The item type ID associated with this summary."""
    start: str
    """The end date of the window as an ISO date string in `YYYY-MM-DD` format."""
    end: str
    """The start date of the window as an ISO date string in `YYYY-MM-DD` format."""
    missing: int
    """The number of dates in the requested window that were missing from the source data."""
    highest: Decimal
    """The volume-weighted average of the daily highest prices in the window."""
    average: Decimal
    """The volume-weighted average of the daily average prices in the window."""
    lowest: Decimal
    """The volume-weighted average of the daily lowest prices in the window."""
    order_count: int
    """The average daily order count across the selected window."""
    volume: Decimal
    """The average daily traded volume across the selected window."""
