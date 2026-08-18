"""Tests for market history summary calculations."""

import pytest

from pfmsoft.eve_argus.data_transform.history_summary import (
    calculate_history_summary,
    calculate_regional_history_summaries,
    date_range_days,
)
from pfmsoft.eve_argus.models.esi.esi_response import (
    GetMarketsRegionIdHistory,
    GetMarketsRegionIdHistoryDetail,
)


def history(
    entries: list[GetMarketsRegionIdHistoryDetail],
) -> GetMarketsRegionIdHistory:
    """Build a history payload for one region and type."""
    return GetMarketsRegionIdHistory(
        received_at="2025-01-03T00:00:00Z",
        expires_at=None,
        region_id=10000002,
        type_id=34,
        history=entries,
    )


def entry(
    date: str,
    *,
    average: float,
    highest: float,
    lowest: float,
    order_count: int,
    volume: int,
) -> GetMarketsRegionIdHistoryDetail:
    """Build one daily history record."""
    return GetMarketsRegionIdHistoryDetail(
        average=average,
        date=date,
        highest=highest,
        lowest=lowest,
        order_count=order_count,
        volume=volume,
    )


@pytest.mark.parametrize(
    ("descending", "expected"),
    [
        (True, ["2025-01-03", "2025-01-02", "2025-01-01"]),
        (False, ["2025-01-03", "2025-01-04", "2025-01-05"]),
    ],
)
def test_date_range_days_generates_requested_direction(
    descending: bool,
    expected: list[str],
) -> None:
    """Date ranges should include the start date and follow the requested direction."""
    assert date_range_days("2025-01-03", 3, descending) == expected


def test_date_range_days_rejects_non_positive_length() -> None:
    """A history window must contain at least one day."""
    with pytest.raises(ValueError, match="positive integer"):
        date_range_days("2025-01-03", 0)


def test_calculate_history_summary_weights_prices_and_counts_missing_days() -> None:
    """Summary prices should be volume weighted across the requested window."""
    market_history = history([
        entry(
            "2025-01-03",
            average=10.0,
            highest=12.0,
            lowest=8.0,
            order_count=10,
            volume=100,
        ),
        entry(
            "2025-01-02",
            average=20.0,
            highest=22.0,
            lowest=18.0,
            order_count=5,
            volume=50,
        ),
    ])

    result = calculate_history_summary(market_history, period=3)

    assert result.start == "2025-01-03"
    assert result.end == "2025-01-01"
    assert result.missing == 1
    assert result.average == pytest.approx(13.3333333333)
    assert result.highest == pytest.approx(15.3333333333)
    assert result.lowest == pytest.approx(11.3333333333)
    assert result.order_count == 5
    assert result.volume == pytest.approx(50.0)


def test_calculate_history_summary_supports_explicit_start_and_zero_volume() -> None:
    """An explicit start date should anchor a zero-volume window without division errors."""
    market_history = history([
        entry(
            "2025-01-01",
            average=10.0,
            highest=10.0,
            lowest=10.0,
            order_count=3,
            volume=0,
        )
    ])

    result = calculate_history_summary(
        market_history,
        period=1,
        start_date="2025-01-01",
    )

    assert (result.average, result.highest, result.lowest) == (0.0, 0.0, 0.0)
    assert result.volume == 0.0


@pytest.mark.parametrize(
    ("history_value", "period", "start_date", "message"),
    [
        (history([]), 1, None, "empty"),
        (history([]), 0, None, "positive integer"),
        (
            history([
                entry(
                    "2025-01-01",
                    average=1,
                    highest=1,
                    lowest=1,
                    order_count=1,
                    volume=1,
                )
            ]),
            1,
            "2025-01-02",
            "not in",
        ),
    ],
)
def test_calculate_history_summary_rejects_invalid_inputs(
    history_value: GetMarketsRegionIdHistory,
    period: int,
    start_date: str | None,
    message: str,
) -> None:
    """Invalid history windows should fail with a useful validation error."""
    with pytest.raises(ValueError, match=message):
        calculate_history_summary(history_value, period, start_date)


def test_calculate_regional_history_summaries_builds_type_mapping() -> None:
    """Regional calculation should summarize every type in its single region."""
    market_history = history([
        entry("2025-01-01", average=4, highest=5, lowest=3, order_count=2, volume=10)
    ])

    result = calculate_regional_history_summaries(
        {10000002: {34: market_history}}, period=1
    )

    assert result.region_id == 10000002
    assert result.summaries[34].average == 4


@pytest.mark.parametrize(
    "regional_histories",
    [{}, {10000002: {}, 10000043: {}}],
)
def test_calculate_regional_history_summaries_rejects_invalid_region_input(
    regional_histories: dict[int, dict[int, GetMarketsRegionIdHistory]],
) -> None:
    """Regional calculation requires exactly one region with history data."""
    with pytest.raises(ValueError):
        calculate_regional_history_summaries(regional_histories, period=1)
