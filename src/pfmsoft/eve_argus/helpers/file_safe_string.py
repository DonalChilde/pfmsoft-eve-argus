"""Helper functions for converting strings to file-safe strings."""

from string import ascii_letters, digits


def file_safe_string(s: str) -> str:
    """Convert a string to a file-safe string.

    Converts a string to a file-safe string by:
    - replacing non-alphanumeric characters with underscores.
    - collapsing multiple consecutive underscores into a single underscore.
    - removing leading and trailing underscores.

    """
    replaced = "".join(c if is_alphanum_or_dash_character(c) else "_" for c in s)
    collapsed = "_".join(part for part in replaced.split("_") if part)
    trimmed = collapsed.strip("_")
    return trimmed


allowed_chars = set(ascii_letters + digits + "-" + "_")


def is_alphanum_or_dash(s: str) -> bool:
    """Check if a string is alphanumeric or contains dashes or underscores."""
    return all(is_alphanum_or_dash_character(c) for c in s)


def is_alphanum_or_dash_character(c: str) -> bool:
    """Check if a character is alphanumeric or a dash or underscore."""
    return c in allowed_chars
