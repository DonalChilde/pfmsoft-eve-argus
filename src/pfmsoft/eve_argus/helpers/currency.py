"""Helper functions for currency conversion between Decimal and integer cents."""

from decimal import ROUND_HALF_UP, Decimal

_CURRENCY_QUANTUM = Decimal("0.01")
_FOUR_PLACES_QUANTUM = Decimal("0.0001")
_DECIMAL_100 = Decimal("100")
_DECIMAL_10000 = Decimal("10000")


def as_currency(value: Decimal) -> Decimal:
    """Round a monetary value to two decimal places.

    This is used as a final step after performing arithmetic operations to ensure that
    monetary values are consistently rounded to two decimal places.
    """
    return value.quantize(_CURRENCY_QUANTUM, rounding=ROUND_HALF_UP)


def to_cents(value: Decimal | float | str) -> int:
    """Quantize ensures 2 decimal places, then convert to integer cents."""
    match value:
        case Decimal():
            decimal_amount = value
        case float() | str():
            decimal_amount = Decimal(str(value))
        case _:
            raise TypeError("Value must be a Decimal, float, or str")
    return int(decimal_amount.quantize(_CURRENCY_QUANTUM) * _DECIMAL_100)


def from_cents(cents: int) -> Decimal:
    """Divide integer cents by Decimal('100') to retain precision."""
    return Decimal(cents) / _DECIMAL_100


def to_four_places(value: Decimal | float | str) -> Decimal:
    """Round a monetary value to four decimal places."""
    match value:
        case Decimal():
            decimal_value = value
        case float() | str():
            decimal_value = Decimal(str(value))
        case _:
            raise TypeError("Value must be a Decimal, float, or str")
    return decimal_value.quantize(_DECIMAL_10000, rounding=ROUND_HALF_UP)


def from_four_places(value: Decimal | int) -> Decimal:
    """Convert a value stored as an integer with four decimal places back to a Decimal."""
    match value:
        case int():
            return Decimal(value) / _DECIMAL_10000
        case Decimal():
            return value.quantize(_FOUR_PLACES_QUANTUM, rounding=ROUND_HALF_UP)
        case _:
            raise TypeError("Value must be an int or Decimal")


def to_precision(amount: Decimal | float | str, precision: int) -> int:
    """Quantize ensures the specified number of decimal places, then convert to integer."""
    if precision <= 0:
        raise ValueError("Precision must be greater than 0")
    if not isinstance(amount, Decimal):
        decimal_amount = Decimal(str(amount))
    else:
        decimal_amount = amount
    quantize_str = "0." + "0" * precision
    return int(decimal_amount.quantize(Decimal(quantize_str)) * (10**precision))


def from_precision(cents: int, precision: int) -> Decimal:
    """Divide integer cents by 10**precision to retain precision."""
    if precision < 0:
        raise ValueError("Precision must be non-negative")
    if precision == 0:
        return Decimal(cents)
    precision_str = "1" + "0" * precision
    return Decimal(cents) / Decimal(precision_str)
