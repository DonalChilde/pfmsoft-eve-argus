"""Tests for dynamic market-history summary calculations."""

from decimal import Decimal

import pytest

from pfmsoft.eve_argus.dynamic.history_summary import (
    calculate_history_summary,
    date_range_days,
)
from pfmsoft.eve_argus.market_history.models import MarketHistoryRecord


def _record(
    *,
    day: str,
    average: str,
    highest: str,
    lowest: str,
    order_count: int,
    volume: int,
    region_id: int = 10000002,
    type_id: int = 34,
    received_at: str = "2026-10-20T12:00:00+00:00",
    expires_at: str | None = "2026-10-21T11:05:00+00:00",
    argus_expires_at: str | None = "2026-10-21T11:05:00+00:00",
) -> MarketHistoryRecord:
    """Build a market-history record with Decimal prices."""
    return MarketHistoryRecord(
        received_at=received_at,
        expires_at=expires_at,
        argus_expires_at=argus_expires_at,
        region_id=region_id,
        type_id=type_id,
        average=Decimal(average),
        date=day,
        highest=Decimal(highest),
        lowest=Decimal(lowest),
        order_count=order_count,
        volume=volume,
    )


RECORDS = (
    _record(
        day="2026-10-18",
        average="4",
        highest="5",
        lowest="3",
        order_count=7,
        volume=10,
    ),
    _record(
        day="2026-10-20",
        average="2",
        highest="3",
        lowest="1",
        order_count=4,
        volume=30,
    ),
    _record(
        day="2026-10-10",
        average="100",
        highest="100",
        lowest="100",
        order_count=100,
        volume=100,
    ),
)


def test_weighted_summary_over_requested_dates() -> None:
    """Prices are volume weighted; counts and volume average over all dates."""
    dates = date_range_days("2026-10-20", 3)
    summary = calculate_history_summary(RECORDS, dates)
    assert summary.region_id == 10000002
    assert summary.type_id == 34
    assert summary.start == "2026-10-20"
    assert summary.end == "2026-10-18"
    assert summary.missing == 1
    assert summary.average == Decimal("2.5")
    assert summary.highest == Decimal("3.5")
    assert summary.lowest == Decimal("1.5")
    assert summary.order_count == 3
    assert summary.volume == Decimal("40") / 3
    assert isinstance(summary.average, Decimal)
    assert isinstance(summary.volume, Decimal)
    assert summary.received_at == "2026-10-20T12:00:00+00:00"
    assert summary.expires_at == "2026-10-21T11:05:00+00:00"
    assert summary.argus_expires_at == "2026-10-21T11:05:00+00:00"


def test_date_order_does_not_change_window_bounds() -> None:
    """Start is the newest requested date and end is the oldest."""
    dates = date_range_days("2026-10-18", 3, descending=False)
    summary = calculate_history_summary(RECORDS, dates)
    assert (summary.start, summary.end) == ("2026-10-20", "2026-10-18")


def test_zero_volume_reports_zero_prices() -> None:
    """Zero valid volume yields zero weighted prices."""
    records = (
        _record(
            day="2026-10-20",
            average="2",
            highest="3",
            lowest="1",
            order_count=5,
            volume=0,
        ),
    )
    summary = calculate_history_summary(records, ["2026-10-20"])
    assert (summary.highest, summary.average, summary.lowest) == (
        Decimal(0),
        Decimal(0),
        Decimal(0),
    )
    assert summary.order_count == 5
    assert summary.volume == Decimal(0)


def test_all_dates_missing() -> None:
    """A window without records is fully missing with zero metrics."""
    summary = calculate_history_summary(RECORDS, ["2026-09-01", "2026-09-02"])
    assert summary.missing == 2
    assert summary.order_count == 0
    assert summary.volume == Decimal(0)
    assert summary.average == Decimal(0)


def test_metadata_comes_from_latest_received_record() -> None:
    """Response metadata is taken from the most recently received record."""
    records = (
        _record(
            day="2026-10-19",
            average="1",
            highest="1",
            lowest="1",
            order_count=1,
            volume=1,
            received_at="2026-10-19T12:00:00+00:00",
            expires_at="2026-10-20T11:05:00+00:00",
            argus_expires_at=None,
        ),
        *RECORDS,
    )
    summary = calculate_history_summary(records, ["2026-10-20"])
    assert summary.received_at == "2026-10-20T12:00:00+00:00"
    assert summary.expires_at == "2026-10-21T11:05:00+00:00"
    assert summary.argus_expires_at == "2026-10-21T11:05:00+00:00"


def test_date_range_days_rejects_non_positive_days() -> None:
    """A date range needs at least one day."""
    with pytest.raises(ValueError, match="positive"):
        date_range_days("2026-10-20", 0)


@pytest.mark.parametrize(
    ("records", "dates", "message"),
    [
        (RECORDS, [], "dates"),
        ((), ["2026-10-20"], "empty"),
        (
            (
                *RECORDS,
                _record(
                    day="2026-10-19",
                    average="1",
                    highest="1",
                    lowest="1",
                    order_count=1,
                    volume=1,
                    region_id=10000043,
                ),
            ),
            ["2026-10-20"],
            "region_id",
        ),
        (
            (
                *RECORDS,
                _record(
                    day="2026-10-19",
                    average="1",
                    highest="1",
                    lowest="1",
                    order_count=1,
                    volume=1,
                    type_id=35,
                ),
            ),
            ["2026-10-20"],
            "type_id",
        ),
    ],
)
def test_invalid_input_raises(
    records: tuple[MarketHistoryRecord, ...], dates: list[str], message: str
) -> None:
    """Empty inputs and mixed region or type records are rejected."""
    with pytest.raises(ValueError, match=message):
        calculate_history_summary(records, dates)
