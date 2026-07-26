"""Data models for calculations."""

from dataclasses import dataclass


@dataclass(slots=True)
class HistorySummaryItem:
    """Represents a summary of market history data for a specific region and type."""

    region_id: int
    type_id: int
    period: int
    start: str
    end: str
    missing: int
    highest: float
    average: float
    lowest: float
    order_count: int
    volume: float
