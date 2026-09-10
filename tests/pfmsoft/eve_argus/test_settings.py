"""Tests for application settings."""

import pytest
from pydantic import ValidationError

from pfmsoft.eve_argus.settings import RateLimitSettings


def test_rate_limit_settings_accepts_positive_finite_values() -> None:
    """Positive finite rate-limit values should be accepted."""
    settings = RateLimitSettings(max_rate=1.5, time_period=2.0)

    assert settings.max_rate == 1.5
    assert settings.time_period == 2.0


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("max_rate", 0),
        ("max_rate", -1),
        ("max_rate", float("nan")),
        ("max_rate", float("inf")),
        ("time_period", 0),
        ("time_period", -1),
        ("time_period", float("nan")),
        ("time_period", float("inf")),
    ),
)
def test_rate_limit_settings_rejects_non_positive_or_non_finite_values(
    field: str, value: float
) -> None:
    """Non-positive and non-finite rate-limit values should be rejected."""
    with pytest.raises(ValidationError):
        RateLimitSettings(**{field: value})
