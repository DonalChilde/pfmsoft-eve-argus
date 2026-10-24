"""Consistent named failure messages across market-history fetch commands."""

from io import StringIO
from unittest.mock import AsyncMock, Mock

import pytest
from rich.console import Console
from typer.testing import CliRunner

from pfmsoft.eve_argus.cli import app
from pfmsoft.eve_argus.cli.fetch import market_history, market_history_active
from pfmsoft.eve_argus.cli.fetch import market_history_bulk as bulk_command
from pfmsoft.eve_argus.cli.fetch._helpers import report_market_history_failure
from pfmsoft.eve_argus.fetch_esi import market_history_bulk as bulk
from pfmsoft.eve_argus.fetch_esi.update import UpdateResult, UpdateStatus
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings
from pfmsoft.eve_argus.static.models import MapRegionsRecord, TypesRecord


@pytest.mark.parametrize("published", [True, False, None])
@pytest.mark.parametrize("message", ["HTTP 404 Not Found", None])
def test_failure_message_format(published: bool | None, message: str | None) -> None:
    """Names are literal, and only explicitly unpublished types get a status label."""
    record = None
    if published is not None:
        record = Mock(spec=TypesRecord)
        record.name = "Compressed [Arkonor] Blueprint"
        record.published = published
    output = StringIO()
    report_market_history_failure(
        messenger=Console(file=output, width=240),
        region_label="The Forge (10000002)",
        type_id=28368,
        type_record=record,
        failure_message=message,
    )
    name = "Unknown type" if record is None else record.name
    status = ", Not Published" if published is False else ""
    assert output.getvalue() == (
        f"Failed: The Forge (10000002), {name} (28368){status}. "
        f"Error Message: {message or 'Update failed.'}\n"
    )


@pytest.mark.parametrize(
    "command_name",
    [
        "market-history",
        "market-history-bulk",
        "market-history-bulk-progress",
        "market-history-active",
    ],
)
@pytest.mark.parametrize("quiet", [False, True])
@pytest.mark.parametrize("published", [True, False])
def test_commands_report_type_names(
    monkeypatch: pytest.MonkeyPatch, command_name: str, quiet: bool, published: bool
) -> None:
    """Every command enriches failures without changing filtering or quiet errors."""
    modules = {
        "market-history": market_history,
        "market-history-bulk": bulk_command,
        "market-history-bulk-progress": bulk_command,
        "market-history-active": market_history_active,
    }
    command = modules[command_name]
    resources = Mock()
    manager = Mock()
    manager.__aenter__ = AsyncMock(return_value=resources)
    manager.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(command, "EveArgusResources", Mock(return_value=manager))
    region = Mock(spec=MapRegionsRecord)
    region.name = "The Forge"
    record = Mock(spec=TypesRecord)
    record.name = "Compressed Arkonor Blueprint"
    record.type_id = 28368
    record.market_group_id = 1
    record.published = published
    reader = Mock(return_value={28368: record})
    monkeypatch.setattr(
        command.static_read, "map_regions", Mock(return_value={10000002: region})
    )
    monkeypatch.setattr(command.static_read, "types", reader)
    if command is bulk_command:
        group = Mock()
        group.market_group_id = 1
        group.int_path = (1,)
        group.types = (28368,)
        monkeypatch.setattr(
            command.static_read, "market_groups", Mock(return_value={1: group})
        )
    if command is market_history_active:
        monkeypatch.setattr(
            command, "_active_type_ids", AsyncMock(return_value={28368})
        )
    updater = AsyncMock(
        return_value=UpdateResult(
            status=UpdateStatus.FAILED,
            previous_state=None,
            failure_message="HTTP 404 Not Found",
        )
    )
    monkeypatch.setattr(bulk, "update_market_history", updater)
    arguments = ["fetch", command_name, "--region-id", "10000002"]
    if command is market_history:
        arguments.extend(["--type-id", "28368"])
    if quiet:
        arguments.append("--quiet")
    result = CliRunner().invoke(
        app, arguments, obj={SETTINGS_KEY: Mock(spec=EveArgusSettings)}
    )
    if command in (bulk_command, market_history_active) and not published:
        assert result.exit_code == 0, result.output
        updater.assert_not_awaited()
        return
    assert result.exit_code == 1, result.output
    status = "" if published else ", Not Published"
    assert (
        "Failed: The Forge (10000002), Compressed Arkonor Blueprint (28368)"
        f"{status}. Error Message: HTTP 404 Not Found"
    ) in " ".join(result.output.split())
    if published:
        assert "Not Published" not in result.output
    reader.assert_called_once_with(
        resources.argus_static_db_connection,
        only_published=command is bulk_command,
    )
    manager.__aexit__.assert_awaited_once()
