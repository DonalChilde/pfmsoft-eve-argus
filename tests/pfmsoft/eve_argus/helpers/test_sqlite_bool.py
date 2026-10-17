"""Tests for strict, nullable SQLite boolean conversions."""

from typing import Any

import pytest

from pfmsoft.eve_argus.helpers.sqlite_bool import bool_to_int, int_to_bool


@pytest.mark.parametrize(("value", "expected"), [(True, 1), (False, 0), (None, None)])
def test_bool_to_int(value: bool | None, expected: int | None) -> None:
    """Convert booleans to actual integers while preserving SQL nulls."""
    result = bool_to_int(value)

    assert result == expected
    assert type(result) is type(expected)


@pytest.mark.parametrize(("value", "expected"), [(1, True), (0, False), (None, None)])
def test_int_to_bool(value: int | None, expected: bool | None) -> None:
    """Convert SQLite integers to actual booleans while preserving SQL nulls."""
    assert int_to_bool(value) is expected


@pytest.mark.parametrize("value", [0, 1, 2, "", "false", [], 0.0])
def test_bool_to_int_rejects_non_booleans(value: Any) -> None:
    """Reject implicit truthiness conversion of non-boolean inputs."""
    with pytest.raises(TypeError, match="bool or None"):
        bool_to_int(value)


@pytest.mark.parametrize("value", [True, False, 0.0, 1.0, "0", "1", []])
def test_int_to_bool_rejects_non_integers(value: Any) -> None:
    """Reject non-integer inputs even when they compare equal to zero or one."""
    with pytest.raises(TypeError, match="int or None"):
        int_to_bool(value)


@pytest.mark.parametrize("value", [-1, 2, 42])
def test_int_to_bool_rejects_invalid_integers(value: int) -> None:
    """Do not interpret invalid database values as true."""
    with pytest.raises(ValueError, match="0 or 1"):
        int_to_bool(value)


@pytest.mark.parametrize("value", [True, False, None])
def test_nullable_round_trip(value: bool | None) -> None:
    """Preserve each supported value across both conversions."""
    assert int_to_bool(bool_to_int(value)) is value
