"""Tests for sequential active-market history fetching and regional failure limits."""

import asyncio
from dataclasses import dataclass
from io import StringIO
from unittest.mock import AsyncMock, Mock

import pytest
import typer
from pfmsoft.eve_link import EsiLink, EsiRequest, EsiResponse, FailedEsiResponse
from rich.console import Console
from rich.progress import Progress, SpinnerColumn
from typer.testing import CliRunner, Result

from pfmsoft.eve_argus.cli import app
from pfmsoft.eve_argus.cli.fetch import market_history_active as command
from pfmsoft.eve_argus.fetch_esi import market_history_bulk as bulk
from pfmsoft.eve_argus.fetch_esi.update import UpdateResult, UpdateStatus
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings
from pfmsoft.eve_argus.static.models import MapRegionsRecord, TypesRecord


def _response(*, region_id: int, type_ids: list[int]) -> Mock:
    """Build a regional ESI response for the real market-types validator."""
    response = Mock(spec=EsiResponse)
    response.esi_request = EsiRequest(
        operation_id="GetMarketsRegionIdTypes",
        path_parameters={"region_id": region_id},
    )
    response.response.metadata.received_at = "2026-10-21T00:00:00Z"
    response.response.metadata.expires_at_instant = None
    response.response_data = type_ids
    return response


@dataclass(slots=True, kw_only=True)
class Environment:
    """Mocked external resources with real discovery and bulk orchestration."""

    settings: EveArgusSettings
    resources: Mock
    manager: Mock
    discovery: AsyncMock
    updater: AsyncMock
    responses: dict[int, Mock]
    events: list[tuple[str, int, int]]
    types: dict[int, Mock]


def _type_record(*, type_id: int, published: bool) -> Mock:
    """Build a static type record with the fields used by the command."""
    record = Mock(spec=TypesRecord)
    record.type_id = type_id
    record.name = f"Type {type_id}"
    record.published = published
    return record


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch) -> Environment:
    """Keep discovery, static reads, and history updates off external services."""
    resources = Mock()
    resources.esi_link = Mock(spec=EsiLink)
    manager = Mock()
    manager.__aenter__ = AsyncMock(return_value=resources)
    manager.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(command, "EveArgusResources", Mock(return_value=manager))
    regions = {}
    for region_id, name in ((100, "First Region"), (200, "Second Region")):
        region = Mock(spec=MapRegionsRecord)
        region.name = name
        regions[region_id] = region
    monkeypatch.setattr(command.static_read, "map_regions", Mock(return_value=regions))
    types = {
        type_id: _type_record(type_id=type_id, published=True)
        for type_id in (10, 11, 12, 13, 20, 21, 34)
    }
    monkeypatch.setattr(command.static_read, "types", Mock(return_value=types))
    responses = {
        100: _response(region_id=100, type_ids=[13, 10, 12, 10]),
        200: _response(region_id=200, type_ids=[21, 20]),
    }
    events: list[tuple[str, int, int]] = []

    async def discover(*, esi_request: EsiRequest, schema: object) -> Mock:
        assert esi_request.operation_id == "GetMarketsRegionIdTypes"
        assert esi_request.query_parameters == {}
        assert schema is resources.esi_schema
        region_id = int(esi_request.path_parameters["region_id"])
        events.append(("discover", region_id, 0))
        return responses[region_id]

    async def update(
        *args: object, region_id: int, type_id: int
    ) -> UpdateResult[object]:
        assert args == (
            resources.esi_link,
            resources.esi_schema,
            resources.market_history_db_connection,
        )
        events.append(("history", region_id, type_id))
        await asyncio.sleep(0)
        events.append(("finished", region_id, type_id))
        return UpdateResult(status=UpdateStatus.SKIPPED, previous_state=None)

    discovery = AsyncMock(side_effect=discover)
    resources.esi_link.make_request = discovery
    updater = AsyncMock(side_effect=update)
    monkeypatch.setattr(bulk, "update_market_history", updater)
    return Environment(
        settings=Mock(spec=EveArgusSettings),
        resources=resources,
        manager=manager,
        discovery=discovery,
        updater=updater,
        responses=responses,
        events=events,
        types=types,
    )


def _invoke(environment: Environment, *arguments: str) -> Result:
    """Invoke the registered command with isolated settings."""
    return CliRunner().invoke(
        app,
        ["fetch", "market-history-active", *arguments],
        obj={SETTINGS_KEY: environment.settings},
    )


def test_regions_are_sequential_and_types_ascending(environment: Environment) -> None:
    """Input region order is retained; duplicates vanish and types start sorted."""
    result = _invoke(
        environment,
        "--region-id",
        "200",
        "--region-id",
        "100",
        "--region-id",
        "200",
    )
    assert result.exit_code == 0, result.output
    assert environment.events == [
        ("discover", 200, 0),
        ("history", 200, 20),
        ("history", 200, 21),
        ("finished", 200, 20),
        ("finished", 200, 21),
        ("discover", 100, 0),
        ("history", 100, 10),
        ("history", 100, 12),
        ("history", 100, 13),
        ("finished", 100, 10),
        ("finished", 100, 12),
        ("finished", 100, 13),
    ]
    assert "Second Region (200)" in result.output
    assert "First Region (100)" in result.output
    environment.manager.__aexit__.assert_awaited_once()


@pytest.mark.parametrize("include_explicit", [False, True])
def test_hubs_select_defined_regions_without_duplicates(
    environment: Environment, monkeypatch: pytest.MonkeyPatch, include_explicit: bool
) -> None:
    """Hub regions follow explicit regions without repeating overlapping selections."""
    regions = {}
    for hub in MARKET_HUBS:
        region = Mock(spec=MapRegionsRecord)
        region.name = hub.region_name
        regions[hub.region_id] = region
        environment.responses[hub.region_id] = _response(
            region_id=hub.region_id, type_ids=[34]
        )
    region = Mock(spec=MapRegionsRecord)
    region.name = "Extra Region"
    regions[100] = region
    monkeypatch.setattr(command.static_read, "map_regions", Mock(return_value=regions))
    hub_ids = list(dict.fromkeys(hub.region_id for hub in MARKET_HUBS))
    explicit = [100, hub_ids[-1]] if include_explicit else []
    arguments = ["--hubs"]
    for region_id in explicit:
        arguments.extend(["--region-id", str(region_id)])
    result = _invoke(environment, *arguments)
    assert result.exit_code == 0, result.output
    assert [
        region_id for event, region_id, _ in environment.events if event == "discover"
    ] == list(dict.fromkeys([*explicit, *hub_ids]))


def test_hubs_validates_all_regions_before_discovery(environment: Environment) -> None:
    """Missing static hub regions fail before discovery, even with explicit regions."""
    result = _invoke(environment, "--hubs", "--region-id", "100")
    assert result.exit_code != 0
    assert "Unknown region IDs" in result.output
    environment.discovery.assert_not_awaited()
    environment.updater.assert_not_awaited()


def test_missing_region_selection_is_reported(environment: Environment) -> None:
    """At least one explicit region or the hubs flag must be selected."""
    result = _invoke(environment, "--quiet")
    assert result.exit_code == 2
    assert "--region-id" in result.output
    assert "--hubs" in result.output
    environment.manager.__aenter__.assert_not_awaited()


@pytest.mark.parametrize(
    "arguments",
    [(), ("--region-id", "bad"), ("--region-id", "100", "--region-id", "999")],
)
def test_invalid_regions_prevent_discovery(
    environment: Environment, arguments: tuple[str, ...]
) -> None:
    """All region IDs are validated before starting any discovery."""
    result = _invoke(environment, *arguments)
    assert result.exit_code != 0
    environment.discovery.assert_not_awaited()
    environment.updater.assert_not_awaited()


def test_empty_region_continues(environment: Environment) -> None:
    """An empty active-type response is a successful regional no-op."""
    environment.responses[100].response_data = []
    result = _invoke(environment, "--region-id", "100", "--region-id", "200")
    assert result.exit_code == 0, result.output
    assert "No active market types" in result.output
    assert [
        call.kwargs["region_id"] for call in environment.updater.await_args_list
    ] == [200, 200]


@pytest.mark.parametrize("quiet", [False, True])
def test_unpublished_excluded_and_unknown_included(
    environment: Environment, quiet: bool
) -> None:
    """Unpublished types are excluded; unknown types are fetched and warned about."""
    environment.types[11] = _type_record(type_id=11, published=False)
    environment.types[20] = _type_record(type_id=20, published=False)
    environment.responses[100].response_data = [13, 11, 10, 999, 998]
    result = _invoke(
        environment,
        "--region-id",
        "100",
        "--region-id",
        "200",
        *(["--quiet"] if quiet else []),
    )
    assert result.exit_code == 0, result.output
    assert [
        (call.kwargs["region_id"], call.kwargs["type_id"])
        for call in environment.updater.await_args_list
    ] == [(100, 10), (100, 13), (100, 998), (100, 999), (200, 21)]
    output = " ".join(result.output.split())
    assert (
        "Warning: First Region (100) has 2 active type IDs missing from the static "
        "types dataset: [998, 999]. Consider updating the static database."
    ) in output
    assert output.count("Warning:") == 1
    if quiet:
        assert "selected" not in output
    else:
        assert "selected 4 active types (2 unknown); excluded 1 unpublished" in output
        assert "selected 1 active types (0 unknown); excluded 1 unpublished" in output


def test_unknown_only_region_is_fetched(environment: Environment) -> None:
    """A region whose active types are all unknown still fetches them."""
    environment.responses[200].response_data = [500]
    result = _invoke(environment, "--region-id", "200")
    assert result.exit_code == 0, result.output
    assert [call.kwargs["type_id"] for call in environment.updater.await_args_list] == [
        500
    ]
    assert "Consider updating the static database." in " ".join(result.output.split())


def test_all_unpublished_region_is_noop(environment: Environment) -> None:
    """A region with only unpublished types is skipped without failing."""
    environment.types[20] = _type_record(type_id=20, published=False)
    environment.types[21] = _type_record(type_id=21, published=False)
    result = _invoke(environment, "--region-id", "200", "--region-id", "100")
    assert result.exit_code == 0, result.output
    assert "No published active market types" in " ".join(result.output.split())
    assert {
        call.kwargs["region_id"] for call in environment.updater.await_args_list
    } == {100}


@pytest.mark.parametrize("failure", ["response", "blank", "malformed", "exception"])
@pytest.mark.parametrize("quiet", [False, True])
def test_discovery_failure_continues(
    environment: Environment, failure: str, quiet: bool
) -> None:
    """Discovery failures stay visible, never become empty successful selections."""
    message = "discovery broke"
    if failure in {"response", "blank"}:
        failed = Mock(spec=FailedEsiResponse)
        failed.failed_response.error_messages = (
            [" ", message] if failure == "response" else [" "]
        )
        environment.responses[100] = failed
        if failure == "blank":
            message = "without an error reason"
    elif failure == "malformed":
        environment.responses[100].response_data = ["not-an-id"]
        message = "GetMarketsRegionIdTypes"
    else:
        environment.discovery.side_effect = [
            RuntimeError(message),
            environment.responses[200],
        ]
    result = _invoke(
        environment,
        "--region-id",
        "100",
        "--region-id",
        "200",
        *(["--quiet"] if quiet else []),
    )
    assert result.exit_code == 1
    assert message in " ".join(result.output.split())
    assert "First Region (100)" in result.output
    assert [
        call.kwargs["region_id"] for call in environment.updater.await_args_list
    ] == [200, 200]
    environment.manager.__aexit__.assert_awaited_once()


@pytest.mark.parametrize("failures_per_region", [1, 2])
def test_failure_budgets_are_independent(
    environment: Environment, monkeypatch: pytest.MonkeyPatch, failures_per_region: int
) -> None:
    """Below-limit failures do not accumulate; aborting one region permits the next."""
    monkeypatch.setattr(bulk, "MARKET_HISTORY_FAILURE_LIMIT", 2)
    monkeypatch.setattr(bulk, "MARKET_HISTORY_BATCH_SIZE", 1)
    for region_id in environment.responses:
        environment.responses[region_id].response_data = [13, 12, 11, 10]

    async def update(
        *args: object, region_id: int, type_id: int
    ) -> UpdateResult[object]:
        return UpdateResult(
            status=UpdateStatus.FAILED
            if type_id < 10 + failures_per_region
            else UpdateStatus.UPDATED,
            previous_state=None,
            failure_message="history broke",
        )

    environment.updater.side_effect = update
    result = _invoke(environment, "--region-id", "200", "--region-id", "100")
    assert result.exit_code == 1
    expected_types = [10, 11] if failures_per_region == 2 else [10, 11, 12, 13]
    assert [
        (call.kwargs["region_id"], call.kwargs["type_id"])
        for call in environment.updater.await_args_list
    ] == [(region, type_id) for region in (200, 100) for type_id in expected_types]
    assert result.output.count("Aborted:") == (2 if failures_per_region == 2 else 0)
    if failures_per_region == 2:
        assert result.output.count("not_started=2") == 2


def test_each_region_has_its_own_progress(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regional progress tracks its own totals and stops before the next region."""
    displays: list[Progress] = []

    def make_progress(*args: object, **kwargs: object) -> Progress:
        progress = Progress(
            SpinnerColumn(), console=Console(file=StringIO()), transient=True
        )
        displays.append(progress)
        return progress

    factory = Mock(side_effect=make_progress)
    monkeypatch.setattr(command, "Progress", factory)
    result = _invoke(environment, "--region-id", "100", "--region-id", "200")
    assert result.exit_code == 0, result.output
    assert factory.call_count == 2
    for progress, expected in zip(displays, [3, 2], strict=True):
        assert not progress.live.is_started
        task = progress.tasks[0]
        assert task.completed == task.total == expected
        assert task.fields["skipped"] == expected
        assert task.fields["updated"] == task.fields["failed"] == 0


def test_quiet_disables_progress(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quiet success has no routine output or live rendering."""
    factory = Mock(wraps=Progress)
    monkeypatch.setattr(command, "Progress", factory)
    result = _invoke(environment, "--region-id", "100", "--quiet")
    assert result.exit_code == 0, result.output
    assert result.output == ""
    assert factory.call_args.kwargs["disable"] is True


@pytest.mark.parametrize("quiet", [False, True])
def test_abort_awaits_cleanup_before_next_discovery(
    environment: Environment,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    quiet: bool,
) -> None:
    """Aborted regions clean up, leave progress incomplete, and retain error output."""
    monkeypatch.setattr(bulk, "MARKET_HISTORY_FAILURE_LIMIT", 1)
    monkeypatch.setattr(bulk, "MARKET_HISTORY_BATCH_SIZE", 3)
    environment.responses[100].response_data = [13, 12, 11, 10]
    displays: list[Progress] = []
    cleaned: set[int] = set()
    original_discover = environment.discovery.side_effect

    def make_progress(*args: object, **kwargs: object) -> Progress:
        progress = Progress(
            SpinnerColumn(), console=Console(file=StringIO()), transient=True
        )
        displays.append(progress)
        return progress

    monkeypatch.setattr(command, "Progress", Mock(side_effect=make_progress))

    async def discover(*, esi_request: EsiRequest, schema: object) -> Mock:
        if esi_request.path_parameters["region_id"] == 200:
            assert cleaned == {11, 12}
            assert not displays[0].live.is_started
        return await original_discover(esi_request=esi_request, schema=schema)

    async def scenario() -> None:
        ready = asyncio.Event()
        blocked = asyncio.Event()
        started = 0

        async def update(
            *args: object, region_id: int, type_id: int
        ) -> UpdateResult[object]:
            nonlocal started
            if region_id == 200:
                return UpdateResult(status=UpdateStatus.UPDATED, previous_state=None)
            started += 1
            if started == 3:
                ready.set()
            try:
                await ready.wait()
                if type_id == 10:
                    raise RuntimeError("history raised")
                await blocked.wait()
            finally:
                if type_id != 10:
                    cleaned.add(type_id)
            return UpdateResult(status=UpdateStatus.SKIPPED, previous_state=None)

        environment.discovery.side_effect = discover
        environment.updater.side_effect = update
        with pytest.raises(typer.Exit) as error:
            await command._fetch_market_history_active(  # pyright: ignore[reportPrivateUsage]
                settings=environment.settings, region_ids=[100, 200], quiet=quiet
            )
        assert error.value.exit_code == 1

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))
    output = " ".join(capsys.readouterr().err.split())
    assert "history raised" in output
    assert "Aborted:" in output
    if not quiet:
        assert "cancelled=2" in output
        assert "not_started=1" in output
    first, second = displays
    assert first.tasks[0].completed == 1
    assert first.tasks[0].total == 4
    assert first.tasks[0].fields["failed"] == 1
    assert second.tasks[0].completed == second.tasks[0].total == 2
    assert second.tasks[0].fields["updated"] == 2
    assert not second.live.is_started


def test_interruption_cleans_up_and_stops_regions(environment: Environment) -> None:
    """Parent cancellation awaits history cleanup and never starts another region."""

    async def scenario() -> None:
        ready = asyncio.Event()
        blocked = asyncio.Event()
        cleaned: set[int] = set()

        async def update(
            *args: object, region_id: int, type_id: int
        ) -> UpdateResult[object]:
            ready.set()
            try:
                await blocked.wait()
            finally:
                cleaned.add(type_id)
            return UpdateResult(status=UpdateStatus.SKIPPED, previous_state=None)

        environment.updater.side_effect = update
        task = asyncio.create_task(
            command._fetch_market_history_active(  # pyright: ignore[reportPrivateUsage]
                settings=environment.settings, region_ids=[100, 200], quiet=True
            )
        )
        await ready.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cleaned == {10, 12, 13}
        environment.discovery.assert_awaited_once()
        environment.manager.__aexit__.assert_awaited_once()

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))
