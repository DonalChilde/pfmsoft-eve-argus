"""Tests for loading and validating fetch selection JSON files."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from pfmsoft.eve_argus.cli.fetch._selection_file import (
    FetchSelection,
    load_selection_file,
    validate_market_type_ids,
    validate_region_ids,
)
from pfmsoft.eve_argus.static.models import TypesRecord


def _write(tmp_path: Path, content: object) -> Path:
    path = tmp_path / "selection.json"
    path.write_text(content if isinstance(content, str) else json.dumps(content))
    return path


def _types() -> dict[int, TypesRecord]:
    types: dict[int, TypesRecord] = {}
    for type_id, group_id, published in (
        (10, 2, True),
        (11, 2, False),
        (13, None, True),
    ):
        record = Mock(spec=TypesRecord)
        record.type_id = type_id
        record.published = published
        record.market_group_id = group_id
        types[type_id] = record
    return types


def test_load_regions_only(tmp_path: Path) -> None:
    """Region IDs keep file order with duplicates removed; extra keys are ignored."""
    path = _write(tmp_path, {"region_ids": [3, 1, 3], "note": "x"})
    assert load_selection_file(path, require_type_ids=False) == FetchSelection(
        region_ids=(3, 1), type_ids=None
    )


def test_load_regions_and_types(tmp_path: Path) -> None:
    """Type IDs are read when present, deduplicated in file order."""
    path = _write(tmp_path, {"region_ids": [1], "type_ids": [12, 10, 12]})
    assert load_selection_file(path, require_type_ids=True) == FetchSelection(
        region_ids=(1,), type_ids=(12, 10)
    )


def test_optional_type_ids_are_still_validated(tmp_path: Path) -> None:
    """A malformed type_ids value fails even when not required."""
    path = _write(tmp_path, {"region_ids": [1], "type_ids": ["10"]})
    with pytest.raises(ValueError, match="type_ids"):
        load_selection_file(path, require_type_ids=False)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{not json", "not valid JSON"),
        ([1, 2], "JSON object"),
        ({}, "region_ids"),
        ({"region_ids": 1}, "region_ids"),
        ({"region_ids": [1, "2"]}, "region_ids"),
        ({"region_ids": [1, True]}, "region_ids"),
        ({"region_ids": [1.0]}, "region_ids"),
        ({"region_ids": []}, "region_ids"),
        ({"region_ids": [1]}, "type_ids"),
        ({"region_ids": [1], "type_ids": []}, "type_ids"),
        ({"region_ids": [1], "type_ids": None}, "type_ids"),
    ],
)
def test_load_rejects_malformed_files(
    tmp_path: Path, content: object, message: str
) -> None:
    """Shape errors name the problem and the file."""
    path = _write(tmp_path, content)
    with pytest.raises(ValueError, match=message) as error:
        load_selection_file(path, require_type_ids=True)
    assert str(path) in str(error.value)


def test_load_missing_file(tmp_path: Path) -> None:
    """Unreadable files raise ValueError."""
    with pytest.raises(ValueError, match="Cannot read"):
        load_selection_file(tmp_path / "missing.json", require_type_ids=False)


def test_validate_region_ids() -> None:
    """Unknown regions are reported together, sorted."""
    validate_region_ids((1, 2), known_region_ids={1, 2, 3})
    with pytest.raises(ValueError, match=r"\[4, 5\]"):
        validate_region_ids((5, 1, 4), known_region_ids={1, 2, 3})


def test_validate_market_type_ids() -> None:
    """Unknown, unpublished, and nonmarket types are reported by category."""
    validate_market_type_ids((10,), types=_types())
    with pytest.raises(ValueError) as error:
        validate_market_type_ids((99, 13, 11, 10), types=_types())
    text = str(error.value)
    assert "unknown type IDs: [99]" in text
    assert "unpublished type IDs: [11]" in text
    assert "nonmarket type IDs: [13]" in text
