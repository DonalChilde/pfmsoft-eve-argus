"""Tests for regional and hub selection in the market-orders command."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, Mock, call

import pytest
from typer.testing import CliRunner

from pfmsoft.eve_argus.cli import app
from pfmsoft.eve_argus.cli.fetch import region_orders as command
from pfmsoft.eve_argus.dynamic.models import MarketOrdersResponse
from pfmsoft.eve_argus.fetch_esi.update import UpdateResult, UpdateStatus
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings


@dataclass(slots=True, kw_only=True)
class CommandEnvironment:
    """Mocked command dependencies without database or network access."""

    settings: EveArgusSettings
    resources: Mock
    factory: Mock
    manager: Mock
    updater: AsyncMock
    order_counter: Mock


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch) -> CommandEnvironment:
    """Replace resource acquisition and the market-order updater."""
    resources = Mock()
    manager = Mock()
    manager.__aenter__ = AsyncMock(return_value=resources)
    manager.__aexit__ = AsyncMock(return_value=False)
    factory = Mock(return_value=manager)
    monkeypatch.setattr(command, "EveArgusResources", factory)
    response = MarketOrdersResponse(
        response_metadata_id=1,
        received_at="2026-10-25T00:00:00Z",
        expires_at=None,
        argus_expires_at=None,
        region_id=10000002,
    )
    updater = AsyncMock(
        return_value=UpdateResult(
            status=UpdateStatus.UPDATED, previous_state=None, new_state=response
        )
    )
    monkeypatch.setattr(command, "update_market_orders", updater)
    order_counter = Mock(return_value=12345)
    monkeypatch.setattr(command.read, "market_order_count", order_counter)
    return CommandEnvironment(
        settings=Mock(spec=EveArgusSettings),
        resources=resources,
        factory=factory,
        manager=manager,
        updater=updater,
        order_counter=order_counter,
    )


@pytest.mark.parametrize(
    ("arguments", "region_ids"),
    [
        (["--region-id", "42"], [42]),
        (["--region-id", "42", "--region-id", "43", "--region-id", "42"], [42, 43]),
        (["--hubs"], list(dict.fromkeys(hub.region_id for hub in MARKET_HUBS))),
        (
            [
                "--region-id",
                "42",
                "--region-id",
                str(MARKET_HUBS[0].region_id),
                "--hubs",
            ],
            list(dict.fromkeys([42, *(hub.region_id for hub in MARKET_HUBS)])),
        ),
    ],
)
def test_fetch_selected_regions(
    environment: CommandEnvironment, arguments: list[str], region_ids: list[int]
) -> None:
    """Fetch each selected region once, in explicit-then-hub order."""
    result = CliRunner().invoke(
        app,
        ["fetch", "market-orders", *arguments],
        obj={SETTINGS_KEY: environment.settings},
    )

    assert result.exit_code == 0, result.output
    assert environment.updater.await_args_list == [
        call(
            environment.resources.esi_link,
            environment.resources.esi_schema,
            environment.resources.argus_dynamic_db_connection,
            region_id=region_id,
        )
        for region_id in region_ids
    ]
    environment.factory.assert_called_once()
    environment.manager.__aexit__.assert_awaited_once()
    assert environment.resources.argus_dynamic_db_connection.mock_calls == []
    assert "Fetched and stored market orders" in result.output
    assert result.output.count("Stored orders: 12,345") == len(region_ids)
    assert environment.order_counter.call_count == len(region_ids)


@pytest.mark.parametrize("quiet", [False, True])
def test_fetch_cached_orders(environment: CommandEnvironment, *, quiet: bool) -> None:
    """Cached responses are reported without reading orders or writing summaries."""
    response = environment.updater.return_value.new_state
    environment.updater.return_value = UpdateResult(
        status=UpdateStatus.SKIPPED, previous_state=response
    )
    result = CliRunner().invoke(
        app,
        [
            "fetch",
            "market-orders",
            "--region-id",
            "42",
            *(["--quiet"] if quiet else []),
        ],
        obj={SETTINGS_KEY: environment.settings},
    )

    assert result.exit_code == 0, result.output
    assert environment.resources.argus_dynamic_db_connection.mock_calls == []
    if quiet:
        assert result.output == ""
    else:
        assert "Using cached market orders for region 42" in result.output
        assert "Stored orders: 12,345" in result.output
    environment.order_counter.assert_called_once_with(
        environment.resources.argus_dynamic_db_connection,
        response_metadata_id=response.response_metadata_id,
    )


def test_fetch_requires_selection(environment: CommandEnvironment) -> None:
    """Missing selection fails before acquiring resources."""
    result = CliRunner().invoke(
        app, ["fetch", "market-orders"], obj={SETTINGS_KEY: environment.settings}
    )

    assert result.exit_code == 2
    assert "Provide at least one --region-id or use --hubs." in result.output
    environment.factory.assert_not_called()
    environment.updater.assert_not_awaited()


def test_legacy_hub_orders_command_is_removed() -> None:
    """Advertise the unified command and reject the removed legacy command."""
    runner = CliRunner()
    help_result = runner.invoke(app, ["fetch", "--help"])
    assert help_result.exit_code == 0
    assert "market-orders" in help_result.output
    assert "hub-orders" not in help_result.output

    result = runner.invoke(app, ["fetch", "hub-orders"])
    assert result.exit_code == 2
    assert "No such command" in result.output


@pytest.mark.parametrize("quiet", [False, True])
def test_fetch_failure_stops_regions(
    environment: CommandEnvironment, *, quiet: bool
) -> None:
    """A failed fetch exits nonzero, reports errors even when quiet, and closes resources."""
    environment.updater.return_value = UpdateResult(
        status=UpdateStatus.FAILED,
        previous_state=None,
        failure_message="ESI unavailable",
    )
    result = CliRunner().invoke(
        app,
        [
            "fetch",
            "market-orders",
            "--region-id",
            "42",
            "--region-id",
            "43",
            *(["--quiet"] if quiet else []),
        ],
        obj={SETTINGS_KEY: environment.settings},
    )

    assert result.exit_code == 1
    assert "ESI unavailable" in result.output
    environment.updater.assert_awaited_once()
    environment.manager.__aexit__.assert_awaited_once()
    environment.order_counter.assert_not_called()


@pytest.mark.parametrize("status", [UpdateStatus.UPDATED, UpdateStatus.SKIPPED])
def test_fetch_missing_response_reports_error_when_quiet(
    environment: CommandEnvironment, *, status: UpdateStatus
) -> None:
    """An invalid update result must not produce a silent or successful exit."""
    environment.updater.return_value = UpdateResult(status=status, previous_state=None)
    result = CliRunner().invoke(
        app,
        ["fetch", "market-orders", "--region-id", "42", "--quiet"],
        obj={SETTINGS_KEY: environment.settings},
    )

    assert result.exit_code == 1
    assert "No market orders for region 42 response is available" in result.output
    environment.manager.__aexit__.assert_awaited_once()
