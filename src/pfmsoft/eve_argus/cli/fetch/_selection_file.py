"""Load and validate region and type selections from a JSON file.

The file contains a top-level object with a ``region_ids`` list of integers and,
for commands that select types, a ``type_ids`` list of integers. Other keys are
ignored, so one file may serve several fetch commands.
"""

import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path

from pfmsoft.eve_argus.static.models import TypesRecord


@dataclass(slots=True, kw_only=True, frozen=True)
class FetchSelection:
    """IDs read from a selection file, deduplicated in file order."""

    region_ids: tuple[int, ...]
    """Region IDs to fetch."""
    type_ids: tuple[int, ...] | None
    """Type IDs to fetch, or None when the file has no ``type_ids`` key."""


def load_selection_file(path: Path, *, require_type_ids: bool) -> FetchSelection:
    """Read a selection file and check its shape.

    Args:
        path: The JSON file to read.
        require_type_ids: Whether a ``type_ids`` key is required.

    Returns:
        The region IDs and, when present, the type IDs.

    Raises:
        ValueError: If the file cannot be read or parsed, is not a JSON object,
            or a required key is missing, empty, or not a list of integers.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"Cannot read selection file {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Selection file {path} is not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"Selection file {path} must contain a JSON object.")
    region_ids = _int_list(data, key="region_ids", path=path)
    type_ids = (
        _int_list(data, key="type_ids", path=path)
        if require_type_ids or "type_ids" in data
        else None
    )
    return FetchSelection(region_ids=region_ids, type_ids=type_ids)


def _int_list(data: Mapping[str, object], *, key: str, path: Path) -> tuple[int, ...]:
    """Return a non-empty list of integers from ``data[key]``, deduplicated."""
    value = data.get(key)
    if (
        not isinstance(value, list)
        or not value
        # bool is a subclass of int, but true/false are not IDs.
        or not all(type(item) is int for item in value)
    ):
        raise ValueError(
            f"Selection file {path} must contain '{key}' as a non-empty list "
            "of integers."
        )
    return tuple(dict.fromkeys(value))


def validate_region_ids(
    region_ids: Collection[int], *, known_region_ids: Collection[int]
) -> None:
    """Check that every region exists in the static database.

    Raises:
        ValueError: If any region ID is unknown.
    """
    unknown = set(region_ids) - set(known_region_ids)
    if unknown:
        raise ValueError(f"Unknown region IDs: {sorted(unknown)}")


def validate_market_type_ids(
    type_ids: Collection[int], *, types: Mapping[int, TypesRecord]
) -> None:
    """Check that every type is a published, market-listed static type.

    Raises:
        ValueError: If any type ID is unknown, unpublished, or not on the market.
    """
    unknown = sorted(type_id for type_id in type_ids if type_id not in types)
    known = [types[type_id] for type_id in type_ids if type_id in types]
    unpublished = sorted(record.type_id for record in known if not record.published)
    nonmarket = sorted(
        record.type_id
        for record in known
        if record.published and record.market_group_id is None
    )
    problems = [
        f"{label} type IDs: {ids}"
        for label, ids in (
            ("unknown", unknown),
            ("unpublished", unpublished),
            ("nonmarket", nonmarket),
        )
        if ids
    ]
    if problems:
        raise ValueError("Invalid selection file types: " + "; ".join(problems))
