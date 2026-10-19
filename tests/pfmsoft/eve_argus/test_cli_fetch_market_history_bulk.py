"""Tests for bulk market-history selection, validation, and CLI reporting."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, Mock

import pytest
from typer.testing import CliRunner

from pfmsoft.eve_argus.cli import app
from pfmsoft.eve_argus.cli.fetch import market_history_bulk as command
from pfmsoft.eve_argus.fetch_esi import market_history_bulk as bulk
from pfmsoft.eve_argus.fetch_esi.update import UpdateResult, UpdateStatus
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings
from pfmsoft.eve_argus.static.models import (
    MapRegionsRecord,
    MarketGroupsDataset,
    MarketGroupsRecord,
    TypesRecord,
)


@dataclass(slots=True, kw_only=True)
class Environment:
    """Isolated external resources and update calls."""

    settings: EveArgusSettings
    updater: AsyncMock
    resources: Mock
    manager: Mock
    groups: MarketGroupsDataset
    types_reader: Mock


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch) -> Environment:
    """Use real path records and mocked static readers/resources."""
    groups = {
        group_id: MarketGroupsRecord(
            market_group_id=group_id,
            description="",
            has_types=bool(types),
            icon_id=None,
            int_path=path,
            name=f"Group {group_id}",
            parent_group_id=path[-2] if len(path) > 1 else None,
            str_path=tuple(str(value) for value in path),
            types=types,
        )
        for group_id, path, types in (
            (1, (1,), ()),
            (2, (1, 2), (10, 11)),
            (3, (1, 3), (12,)),
            (4, (4,), (13,)),
        )
    }
    types = {}
    for type_id, group_id in ((10, 2), (12, 3), (13, 4), (14, None)):
        record = Mock(spec=TypesRecord)
        record.type_id = type_id
        record.market_group_id = group_id
        record.published = True
        types[type_id] = record
    regions = {}
    for region_id, name in ((100, "First Region"), (200, "Second Region")):
        region = Mock(spec=MapRegionsRecord)
        region.region_id = region_id
        region.name = name
        regions[region_id] = region
    resources = Mock()
    manager = Mock()
    manager.__aenter__ = AsyncMock(return_value=resources)
    manager.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(command, "EveArgusResources", Mock(return_value=manager))
    types_reader = Mock(return_value=types)
    monkeypatch.setattr(command.static_read, "types", types_reader)
    monkeypatch.setattr(command.static_read, "market_groups", Mock(return_value=groups))
    monkeypatch.setattr(command.static_read, "map_regions", Mock(return_value=regions))
    updater = AsyncMock(
        return_value=UpdateResult(status=UpdateStatus.SKIPPED, previous_state=None)
    )
    monkeypatch.setattr(bulk, "update_market_history", updater)
    return Environment(
        settings=Mock(spec=EveArgusSettings),
        updater=updater,
        resources=resources,
        manager=manager,
        groups=groups,
        types_reader=types_reader,
    )


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (list[str](), {10, 12, 13}),
        (["--include", "1"], {10, 12}),
        (["--include", "2", "--include", "4"], {10, 13}),
        (["--exclude", "1"], {13}),
        (["--exclude", "2", "--include", "1", "--include", "2"], {12}),
        (["--include", "2", "--exclude", "2"], set[int]()),
        (["--include", "2", "--include", "2"], {10}),
    ],
)
def test_selects_published_market_types(
    environment: Environment, *, filters: list[str], expected: set[int]
) -> None:
    """Published nonmarket and unpublished market types are never requested."""
    result = CliRunner().invoke(
        app,
        [
            "fetch",
            "market-history-bulk",
            "--region-id",
            "100",
            "--region-id",
            "200",
            "--region-id",
            "100",
            *filters,
        ],
        obj={SETTINGS_KEY: environment.settings},
    )
    assert result.exit_code == 0, result.output
    actual = {
        (call.kwargs["region_id"], call.kwargs["type_id"])
        for call in environment.updater.await_args_list
    }
    assert actual == {
        (region, type_id) for region in (100, 200) for type_id in expected
    }
    assert environment.updater.await_count == len(actual)
    for call in environment.updater.await_args_list:
        assert call.args == (
            environment.resources.esi_link,
            environment.resources.esi_schema,
            environment.resources.market_history_db_connection,
        )
    environment.types_reader.assert_called_once_with(
        environment.resources.argus_static_db_connection, only_published=True
    )
    assert "First Region (100)" in result.output
    assert "Second Region (200)" in result.output
    if not expected:
        assert "No market types selected" in result.output
    environment.manager.__aexit__.assert_awaited_once()


@pytest.mark.parametrize(
    ("arguments", "messages"),
    [
        (["--region-id", "999", "--region-id", "998"], ["998", "999"]),
        (
            ["--region-id", "100", "--include", "999", "--exclude", "998"],
            ["998", "999"],
        ),
        ([], ["--region-id"]),
        (["--region-id", "bad"], ["Invalid"]),
    ],
)
def test_invalid_inputs_prevent_updates(
    environment: Environment, *, arguments: list[str], messages: list[str]
) -> None:
    """Invalid regions and filters fail before any history request."""
    result = CliRunner().invoke(
        app,
        ["fetch", "market-history-bulk", *arguments],
        obj={SETTINGS_KEY: environment.settings},
    )
    assert result.exit_code != 0
    for message in messages:
        assert message in result.output
    environment.updater.assert_not_awaited()


@pytest.mark.parametrize("quiet", [False, True])
def test_partial_failure_and_abort_reporting(
    environment: Environment, monkeypatch: pytest.MonkeyPatch, *, quiet: bool
) -> None:
    """Failures are visible even when quiet, with named regions and nonzero exit."""
    monkeypatch.setattr(bulk, "MARKET_HISTORY_FAILURE_LIMIT", 2)
    environment.updater.side_effect = [
        UpdateResult(status=UpdateStatus.UPDATED, previous_state=None),
        UpdateResult(
            status=UpdateStatus.FAILED, previous_state=None, failure_message="boom"
        ),
        RuntimeError("fetch exception"),
    ]
    result = CliRunner().invoke(
        app,
        [
            "fetch",
            "market-history-bulk",
            "--region-id",
            "100",
            *(["--quiet"] if quiet else []),
        ],
        obj={SETTINGS_KEY: environment.settings},
    )
    assert result.exit_code == 1
    assert "boom" in result.output
    assert "fetch exception" in result.output
    assert "First Region (100)" in result.output
    assert "Aborted" in result.output
    if not quiet:
        assert "updated=1" in result.output
        assert "failed=2" in result.output
    environment.manager.__aexit__.assert_awaited_once()


def test_quiet_success(environment: Environment) -> None:
    """Quiet mode produces no routine output."""
    result = CliRunner().invoke(
        app,
        ["fetch", "market-history-bulk", "--region-id", "100", "--quiet"],
        obj={SETTINGS_KEY: environment.settings},
    )
    assert result.exit_code == 0, result.output
    assert result.output == ""


def test_broken_group_reference(environment: Environment) -> None:
    """Published types listed in a different market group are invalid static data."""
    environment.groups[2].types = (10, 14)
    result = CliRunner().invoke(
        app,
        ["fetch", "market-history-bulk", "--region-id", "100"],
        obj={SETTINGS_KEY: environment.settings},
    )
    assert result.exit_code != 0
    assert "14" in result.output
    environment.updater.assert_not_awaited()


@pytest.mark.parametrize("dataset", ["types", "market_groups", "map_regions"])
def test_missing_static_data(
    environment: Environment, monkeypatch: pytest.MonkeyPatch, *, dataset: str
) -> None:
    """Missing static data is an explicit error rather than an empty success."""
    monkeypatch.setattr(command.static_read, dataset, Mock(return_value={}))
    result = CliRunner().invoke(
        app,
        ["fetch", "market-history-bulk", "--region-id", "100", "--quiet"],
        obj={SETTINGS_KEY: environment.settings},
    )
    assert result.exit_code != 0
    assert result.output
    environment.updater.assert_not_awaited()


def test_failure_below_limit_continues(environment: Environment) -> None:
    """A failed pair does not stop subsequent pairs, but makes the exit nonzero."""
    environment.updater.side_effect = [
        UpdateResult(
            status=UpdateStatus.FAILED, previous_state=None, failure_message="boom"
        ),
        UpdateResult(status=UpdateStatus.UPDATED, previous_state=None),
        UpdateResult(status=UpdateStatus.SKIPPED, previous_state=None),
    ]
    result = CliRunner().invoke(
        app,
        ["fetch", "market-history-bulk", "--region-id", "100"],
        obj={SETTINGS_KEY: environment.settings},
    )
    assert result.exit_code == 1
    assert environment.updater.await_count == 3
    assert "updated=1" in result.output
    assert "skipped=1" in result.output
    assert "failed=1" in result.output
    assert "cancelled=0" in result.output
    assert "not_started=0" in result.output
    assert "Aborted" not in result.output


def test_invalid_market_path(environment: Environment) -> None:
    """Missing path ancestors are rejected before applying filters."""
    environment.groups[2].int_path = (999, 2)
    result = CliRunner().invoke(
        app,
        ["fetch", "market-history-bulk", "--region-id", "100"],
        obj={SETTINGS_KEY: environment.settings},
    )
    assert result.exit_code != 0
    assert "Invalid market path" in result.output
    environment.updater.assert_not_awaited()
