"""Pytest configuration for custom options and test selection."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


@dataclass(frozen=True, slots=True, kw_only=True)
class MarkerFlagOption:
    """Configuration for a boolean CLI flag that gates a pytest marker."""

    option: str
    marker_name: str
    help_text: str
    skip_reason: str
    marker_description: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FixtureValueOption:
    """Configuration for a CLI value provided to tests through a fixture."""

    option: str
    help_text: str
    value_type: Callable[[str], Any]
    metavar: str


_MARKER_FLAG_OPTIONS: tuple[MarkerFlagOption, ...] = (
    MarkerFlagOption(
        option="--runslow",
        marker_name="slow",
        help_text="run slow tests",
        skip_reason="need --runslow option to run",
        marker_description="mark test as slow to run",
    ),
    MarkerFlagOption(
        option="--runlive",
        marker_name="live",
        help_text="run live network tests",
        skip_reason="need --runlive option to run",
        marker_description="mark test as live network test",
    ),
)

_ESD_STATIC_DB_OPTION = FixtureValueOption(
    option="--esd-static-db",
    help_text="provide the ESD static database path to tests",
    value_type=Path,
    metavar="PATH",
)
_FIXTURE_VALUE_OPTIONS: tuple[FixtureValueOption, ...] = (_ESD_STATIC_DB_OPTION,)


# ---------------------------------------------------------------------------------
# Add options to control test execution and provide values to fixtures.
# ---------------------------------------------------------------------------------
def pytest_addoption(parser: pytest.Parser) -> None:
    """Add marker-gating flags and fixture-value CLI options.

    Example CLI usage:
        Run tests with default marker gating:
            pytest

        Include slow tests guarded by the `slow` marker:
            pytest --runslow

        Provide a path to a test that requests `esd_static_db_path`:
            pytest --esd-static-db /path/to/esd-static.sqlite

    Example targeted test usage:
        Run one slow-marked test explicitly once the flag is enabled:
            pytest tests/path/to/test_module.py -k slow_case --runslow

        Run only tests marked `slow`:
            pytest -m slow --runslow

        Run a test that requests `esd_static_db_path`:
            pytest tests/path/to/test_module.py --esd-static-db /path/to/esd-static.sqlite

    Example Python usage:
        ```python
        import pytest


        @pytest.mark.slow
        def test_expensive_case() -> None:
            assert True


        def test_static_data(esd_static_db_path) -> None:
            assert esd_static_db_path.is_file()
        ```
    """
    # https://docs.pytest.org/en/stable/example/simple.html#control-skipping-of-tests-according-to-command-line-option
    # conftest.py must be in the root test package.
    for marker_option in _MARKER_FLAG_OPTIONS:
        parser.addoption(
            marker_option.option,
            action="store_true",
            default=False,
            help=marker_option.help_text,
        )
    for value_option in _FIXTURE_VALUE_OPTIONS:
        parser.addoption(
            value_option.option,
            action="store",
            default=None,
            type=value_option.value_type,
            metavar=value_option.metavar,
            help=value_option.help_text,
        )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers controlled by command line flags."""
    for marker_option in _MARKER_FLAG_OPTIONS:
        config.addinivalue_line(
            "markers",
            f"{marker_option.marker_name}: {marker_option.marker_description}",
        )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Apply skip markers for gated tests when their CLI flag is absent."""
    for marker_option in _MARKER_FLAG_OPTIONS:
        if config.getoption(marker_option.option):
            continue
        skip_marker = pytest.mark.skip(reason=marker_option.skip_reason)
        for item in items:
            if marker_option.marker_name in item.keywords:
                item.add_marker(skip_marker)


# ---------------------------------------------------------------------------------
@pytest.fixture(scope="session")
def esd_static_db_path(request: pytest.FixtureRequest) -> Path:
    """Fixture to provide the path to the ESD static database."""
    path = request.config.getoption(_ESD_STATIC_DB_OPTION.option)
    if path is None:
        pytest.skip("no --esd-static-db path provided")

    if not path.is_file():
        pytest.fail(f"--esd-static-db path does not exist or is not a file: {path}")
    return path
