"""Pytest configuration for test selection markers."""

from dataclasses import dataclass

import pytest


@dataclass(frozen=True, slots=True)
class SkipMarkerOption:
    """Configuration describing one CLI-gated pytest marker."""

    option: str
    marker_name: str
    help_text: str
    skip_reason: str
    marker_description: str


_SKIP_MARKER_OPTIONS: tuple[SkipMarkerOption, ...] = (
    SkipMarkerOption(
        option="--runslow",
        marker_name="slow",
        help_text="run slow tests",
        skip_reason="need --runslow option to run",
        marker_description="mark test as slow to run",
    ),
    SkipMarkerOption(
        option="--runlive",
        marker_name="live",
        help_text="run live network tests",
        skip_reason="need --runlive option to run",
        marker_description="mark test as live network test",
    ),
)


# ---------------------------------------------------------------------------------
# Add options to control test execution. Requires the associated flag to be passed on
# the pytest cli in order to run the tests.
# ---------------------------------------------------------------------------------
def pytest_addoption(parser: pytest.Parser) -> None:
    """Add command line options that gate marked tests.

    Example CLI usage:
        ./tests with default marker gating:
            pytest

        Include slow tests guarded by the `slow` marker:
            pytest --runslow

    Example targeted test usage:
        Run one slow-marked test explicitly once the flag is enabled:
            pytest tests/path/to/test_module.py -k slow_case --runslow

        Run only tests marked `slow`:
            pytest -m slow --runslow

    Example Python usage:
        ```python
        import pytest


        @pytest.mark.slow
        def test_expensive_case() -> None:
            assert True
        ```
    """
    # https://docs.pytest.org/en/stable/example/simple.html#control-skipping-of-tests-according-to-command-line-option
    # conftest.py must be in the root test package.
    for marker_option in _SKIP_MARKER_OPTIONS:
        parser.addoption(
            marker_option.option,
            action="store_true",
            default=False,
            help=marker_option.help_text,
        )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers controlled by command line flags."""
    for marker_option in _SKIP_MARKER_OPTIONS:
        config.addinivalue_line(
            "markers",
            f"{marker_option.marker_name}: {marker_option.marker_description}",
        )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Apply skip markers for gated tests when their CLI flag is absent."""
    for marker_option in _SKIP_MARKER_OPTIONS:
        if config.getoption(marker_option.option):
            continue
        skip_marker = pytest.mark.skip(reason=marker_option.skip_reason)
        for item in items:
            if marker_option.marker_name in item.keywords:
                item.add_marker(skip_marker)


# ---------------------------------------------------------------------------------
