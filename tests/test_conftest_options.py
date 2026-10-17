"""Tests for custom pytest options configured in conftest."""

from pathlib import Path
from typing import Any

import pytest

from tests.conftest import (
    esd_static_db_path,
    pytest_addoption,
    pytest_collection_modifyitems,
)


class FakeParser:
    """Capture pytest option declarations."""

    def __init__(self) -> None:
        """Initialize the captured option state."""
        self.options: dict[str, dict[str, Any]] = {}

    def addoption(self, option: str, **kwargs: Any) -> None:
        """Record an option declaration."""
        self.options[option] = kwargs


class FakeConfig:
    """Provide option values to pytest hooks and fixtures."""

    def __init__(self, options: dict[str, Any]) -> None:
        """Initialize the configured option values."""
        self.options = options

    def getoption(self, option: str) -> Any:
        """Return a configured option value."""
        return self.options[option]


class FakeItem:
    """Capture skip markers added by collection modification."""

    def __init__(self, keywords: set[str]) -> None:
        """Initialize the item keywords and marker collection."""
        self.keywords = keywords
        self.markers: list[Any] = []

    def add_marker(self, marker: Any) -> None:
        """Record a marker added during collection."""
        self.markers.append(marker)


class FakeRequest:
    """Provide a fake pytest request to the path fixture."""

    def __init__(self, options: dict[str, Any]) -> None:
        """Initialize the request with its configuration options."""
        self.config = FakeConfig(options)


def test_addoption_registers_flags_and_path_value() -> None:
    """Register marker flags as booleans and the database option as a path."""
    parser = FakeParser()

    pytest_addoption(parser)  # type: ignore[arg-type]

    assert parser.options["--runslow"]["action"] == "store_true"
    assert parser.options["--runlive"]["action"] == "store_true"
    assert parser.options["--esd-static-db"]["action"] == "store"
    assert parser.options["--esd-static-db"]["type"] is Path
    assert parser.options["--esd-static-db"]["default"] is None
    assert parser.options["--esd-static-db"]["metavar"] == "PATH"


def test_collection_skips_only_marked_tests_without_their_flag() -> None:
    """Apply marker skips independently for each disabled flag."""
    slow_item = FakeItem({"slow"})
    live_item = FakeItem({"live"})
    ordinary_item = FakeItem(set())
    config = FakeConfig({"--runslow": True, "--runlive": False})

    pytest_collection_modifyitems(
        config,  # type: ignore[arg-type]
        [slow_item, live_item, ordinary_item],  # type: ignore[arg-type]
    )

    assert not slow_item.markers
    assert len(live_item.markers) == 1
    assert not ordinary_item.markers


def test_esd_static_db_path_skips_when_option_is_missing() -> None:
    """Skip tests requesting the database fixture if no path was supplied."""
    request = FakeRequest({"--esd-static-db": None})

    with pytest.raises(pytest.skip.Exception, match="no --esd-static-db path"):
        esd_static_db_path.__wrapped__(request)  # type: ignore[attr-defined]


def test_esd_static_db_path_returns_existing_file(tmp_path: Path) -> None:
    """Return the configured database file path."""
    path = tmp_path / "static.sqlite"
    path.touch()
    request = FakeRequest({"--esd-static-db": path})

    result = esd_static_db_path.__wrapped__(request)  # type: ignore[attr-defined]

    assert result == path


def test_esd_static_db_path_fails_for_non_file(tmp_path: Path) -> None:
    """Fail with a clear message when the configured path is not a file."""
    path = tmp_path / "missing.sqlite"
    request = FakeRequest({"--esd-static-db": path})

    with pytest.raises(pytest.fail.Exception, match="does not exist or is not a file"):
        esd_static_db_path.__wrapped__(request)  # type: ignore[attr-defined]
