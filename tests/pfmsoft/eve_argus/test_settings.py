"""Tests for application settings."""

import pytest
from pydantic import ValidationError

from pfmsoft.eve_argus.settings import (
    TOML_SETTINGS_FILE,
    EveArgusTomlSettings,
    RateLimitSettings,
    get_settings,
)


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


def test_rate_limit_settings_rejects_extra_fields() -> None:
    """Unknown rate-limit fields should be rejected rather than ignored."""
    with pytest.raises(ValidationError):
        RateLimitSettings(maxrate=7.0)


def test_toml_settings_rejects_extra_fields() -> None:
    """Unknown top-level TOML fields should be rejected rather than ignored."""
    with pytest.raises(ValidationError):
        EveArgusTomlSettings(rate_limit=RateLimitSettings(), retries=3)


def test_toml_settings_defaults_missing_rate_limit_table() -> None:
    """A missing rate-limit table should use its field defaults."""
    settings = EveArgusTomlSettings.model_validate({})

    assert settings.rate_limit == RateLimitSettings()


def test_toml_settings_defaults_missing_rate_limit_field() -> None:
    """A missing rate-limit field should use its field default."""
    settings = EveArgusTomlSettings.model_validate({"rate_limit": {"max_rate": 7.5}})

    assert settings.rate_limit.max_rate == 7.5
    assert settings.rate_limit.time_period == 1.0


def test_get_settings_rejects_toml_directory(tmp_path) -> None:
    """A directory at the TOML configuration path should raise an error."""
    (tmp_path / TOML_SETTINGS_FILE).mkdir()

    with pytest.raises(ValueError, match="is not a file"):
        get_settings(tmp_path)
