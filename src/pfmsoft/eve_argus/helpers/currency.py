"""Helper functions for currency conversion between Decimal and integer cents."""

from decimal import Decimal


def to_cents(amount: Decimal | float | str) -> int:
    """Quantize ensures 2 decimal places, then convert to integer cents."""
    if not isinstance(amount, Decimal):
        decimal_amount = Decimal(str(amount))
    else:
        decimal_amount = amount
    return int(decimal_amount.quantize(Decimal("0.01")) * 100)


def from_cents(cents: int) -> Decimal:
    """Divide integer cents by Decimal('100') to retain precision."""
    return Decimal(cents) / Decimal("100")


def to_cents_precision(amount: Decimal | float | str, precision: int) -> int:
    """Quantize ensures the specified number of decimal places, then convert to integer cents."""
    if precision <= 0:
        raise ValueError("Precision must be greater than 0")
    if not isinstance(amount, Decimal):
        decimal_amount = Decimal(str(amount))
    else:
        decimal_amount = amount
    quantize_str = "0." + "0" * precision
    return int(decimal_amount.quantize(Decimal(quantize_str)) * (10**precision))


def from_cents_precision(cents: int, precision: int) -> Decimal:
    """Divide integer cents by 10**precision to retain precision."""
    if precision < 0:
        raise ValueError("Precision must be non-negative")
    if precision == 0:
        return Decimal(cents)
    precision_str = "1" + "0" * precision
    return Decimal(cents) / Decimal(precision_str)
