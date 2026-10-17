"""Convert between Python booleans and SQLite integers without losing nulls."""

from typing import overload


@overload
def bool_to_int(value: bool) -> int: ...


@overload
def bool_to_int(value: None) -> None: ...


def bool_to_int(value: bool | None) -> int | None:
    """Convert True/False to 1/0, preserving None as SQL NULL.

    Raises:
        TypeError: If value is neither a boolean nor None.
    """
    if value is None:
        return None
    if type(value) is not bool:
        raise TypeError(f"Expected bool or None, got {type(value).__name__}")
    return int(value)


@overload
def int_to_bool(value: int) -> bool: ...


@overload
def int_to_bool(value: None) -> None: ...


def int_to_bool(value: int | None) -> bool | None:
    """Convert 1/0 to True/False, preserving SQL NULL as None.

    Raises:
        TypeError: If value is neither an integer nor None, including booleans.
        ValueError: If the integer is not 0 or 1.
    """
    if value is None:
        return None
    if type(value) is not int:
        raise TypeError(f"Expected int or None, got {type(value).__name__}")
    if value not in (0, 1):
        raise ValueError(f"Expected 0 or 1, got {value}")
    return bool(value)
