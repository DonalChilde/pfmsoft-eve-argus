"""Tests for the single-pair market-history fetch command."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, Mock

import pytest
from typer.testing import CliRunner

from pfmsoft.eve_argus.cli import app
from pfmsoft.eve_argus.fetch_esi import market_history_bulk as bulk
from pfmsoft.eve_argus.fetch_esi.update import UpdateResult, UpdateStatus
from pfmsoft.eve_argus.market_history.models import MarketHistoryResponse
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings


@dataclass(slots=True, kw_only=True)
class CommandEnvironment:
    """Mocked settings, resources, and updater for CLI tests."""

    settings: EveArgusSettings
    resources: Mock
    manager: Mock
    updater: AsyncMock


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch) -> CommandEnvironment:
    """Replace resource acquisition and ESI updates without live access."""
    from pfmsoft.eve_argus.cli.fetch import market_history as command

    resources = Mock()
    manager = Mock()
    manager.__aenter__ = AsyncMock(return_value=resources)
    manager.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(command, "EveArgusResources", Mock(return_value=manager))
    monkeypatch.setattr(command.static_read, "types", Mock(return_value={}))
    monkeypatch.setattr(command.static_read, "map_regions", Mock(return_value={}))
    updater = AsyncMock()
    monkeypatch.setattr(bulk, "update_market_history", updater)
    return CommandEnvironment(
        settings=Mock(spec=EveArgusSettings),
        resources=resources,
        manager=manager,
        updater=updater,
    )


@pytest.mark.parametrize("status", [UpdateStatus.UPDATED, UpdateStatus.SKIPPED])
@pytest.mark.parametrize("quiet", [False, True])
def test_fetch_reports_success(
    environment: CommandEnvironment, *, status: UpdateStatus, quiet: bool
) -> None:
    """The registered command passes one pair and the history database to updates."""
    response = MarketHistoryResponse(
        response_metadata_id=1,
        received_at="2026-10-18T00:00:00Z",
        expires_at="2999-01-01T00:00:00Z",
        argus_expires_at=None,
        region_id=10000002,
        type_id=34,
        response_count=1,
    )
    environment.updater.return_value = UpdateResult(
        status=status,
        previous_state=response if status is UpdateStatus.SKIPPED else None,
        new_state=response if status is UpdateStatus.UPDATED else None,
    )

    result = CliRunner().invoke(
        app,
        [
            "fetch",
            "market-history",
            "--region-id",
            "10000002",
            "--type-id",
            "34",
            *(["--quiet"] if quiet else []),
        ],
        obj={SETTINGS_KEY: environment.settings},
    )

    assert result.exit_code == 0, result.output
    environment.updater.assert_awaited_once_with(
        environment.resources.esi_link,
        environment.resources.esi_schema,
        environment.resources.market_history_db_connection,
        region_id=10000002,
        type_id=34,
    )
    environment.manager.__aexit__.assert_awaited_once()
    if quiet:
        assert result.output == ""
    elif status is UpdateStatus.UPDATED:
        assert "Fetched and stored market history" in result.output
    else:
        assert "Using cached market history" in result.output


@pytest.mark.parametrize("quiet", [False, True])
def test_fetch_failure_is_visible(
    environment: CommandEnvironment, *, quiet: bool
) -> None:
    """Failed updates exit nonzero and remain visible in quiet mode."""
    environment.updater.return_value = UpdateResult(
        status=UpdateStatus.FAILED,
        previous_state=None,
        failure_message="ESI unavailable",
    )
    result = CliRunner().invoke(
        app,
        [
            "fetch",
            "market-history",
            "--region-id",
            "10000002",
            "--type-id",
            "34",
            *(["--quiet"] if quiet else []),
        ],
        obj={SETTINGS_KEY: environment.settings},
    )

    assert result.exit_code == 1
    output = " ".join(result.output.split())
    assert "ESI unavailable" in output
    assert "Unknown region (10000002), Unknown type (34)." in output
    assert "Not Published" not in output
    environment.manager.__aexit__.assert_awaited_once()


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--region-id", "10000002"],
        ["--type-id", "34"],
        ["--region-id", "invalid", "--type-id", "34"],
    ],
)
def test_fetch_requires_both_integer_ids(
    environment: CommandEnvironment, *, arguments: list[str]
) -> None:
    """Invalid or missing IDs are rejected before acquiring external resources."""
    result = CliRunner().invoke(
        app,
        ["fetch", "market-history", *arguments],
        obj={SETTINGS_KEY: environment.settings},
    )

    assert result.exit_code == 2
    environment.manager.__aenter__.assert_not_awaited()
    environment.updater.assert_not_awaited()
