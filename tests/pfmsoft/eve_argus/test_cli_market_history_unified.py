"""Tests for unified history selection, regional execution, and output."""

import asyncio
from dataclasses import dataclass
from io import StringIO
from unittest.mock import AsyncMock, Mock

import pytest
from rich.console import Console
from rich.progress import Progress, ProgressColumn
from typer.testing import CliRunner, Result

from pfmsoft.eve_argus.cli import app
from pfmsoft.eve_argus.cli.fetch import market_history as command
from pfmsoft.eve_argus.fetch_esi import market_history_bulk as bulk
from pfmsoft.eve_argus.fetch_esi.update import UpdateResult, UpdateStatus
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings
from pfmsoft.eve_argus.static.models import MarketGroupsRecord, TypesRecord


@dataclass(slots=True, kw_only=True)
class Environment:
    """External resources replaced with mocks."""

    settings: EveArgusSettings
    manager: Mock
    resources: Mock
    updater: AsyncMock
    discovery: AsyncMock
    types: dict[int, TypesRecord]


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch) -> Environment:
    """Provide two regions and market groups with published and unknown types."""
    resources = Mock()
    manager = Mock()
    manager.__aenter__ = AsyncMock(return_value=resources)
    manager.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(command, "EveArgusResources", Mock(return_value=manager))
    regions = {}
    for region_id in (100, 200, *(hub.region_id for hub in MARKET_HUBS)):
        region = Mock()
        region.name = f"Region {region_id}"
        regions[region_id] = region
    monkeypatch.setattr(command.static_read, "map_regions", Mock(return_value=regions))
    types: dict[int, TypesRecord] = {}
    for type_id, group_id, published in (
        (10, 2, True),
        (11, 2, False),
        (12, 3, True),
        (13, None, True),
    ):
        record = Mock(spec=TypesRecord)
        record.type_id = type_id
        record.name = f"Type {type_id}"
        record.published = published
        record.market_group_id = group_id
        types[type_id] = record
    monkeypatch.setattr(command.static_read, "types", Mock(return_value=types))
    groups = {
        group_id: MarketGroupsRecord(
            market_group_id=group_id,
            description="",
            has_types=bool(ids),
            icon_id=None,
            int_path=path,
            name=f"Group {group_id}",
            parent_group_id=path[-2] if len(path) > 1 else None,
            str_path=tuple(map(str, path)),
            types=ids,
        )
        for group_id, path, ids in (
            (1, (1,), ()),
            (2, (1, 2), (10, 11)),
            (3, (1, 3), (12,)),
        )
    }
    monkeypatch.setattr(command.static_read, "market_groups", Mock(return_value=groups))
    updater = AsyncMock(
        return_value=UpdateResult(status=UpdateStatus.SKIPPED, previous_state=None)
    )
    monkeypatch.setattr(bulk, "update_market_history", updater)
    discovery = AsyncMock(return_value={10, 11, 12, 13, 99})
    monkeypatch.setattr(command, "active_type_ids", discovery)
    return Environment(
        settings=Mock(spec=EveArgusSettings),
        manager=manager,
        resources=resources,
        updater=updater,
        discovery=discovery,
        types=types,
    )


def _invoke(environment: Environment, *arguments: str) -> Result:
    """Invoke the registered command without application initialization."""
    return CliRunner().invoke(
        app,
        ["fetch", "market-history", *arguments],
        obj={SETTINGS_KEY: environment.settings},
    )


def test_help_exposes_unified_options(environment: Environment) -> None:
    """Registered help exposes all supported modes and configurable limits."""
    result = _invoke(environment, "--help")
    assert result.exit_code == 0, result.output
    for option in (
        "--region-id",
        "--hubs",
        "--type-id",
        "--active",
        "--market-types",
        "--industry-types",
        "--include",
        "--exclude",
        "--batch-size",
        "--failure-limit",
        "--progress",
        "--quiet",
    ):
        assert option in result.output
    assert "--all-market-types" not in result.output
    assert "--all-industry-types" not in result.output
    environment.manager.__aenter__.assert_not_awaited()


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--region-id", "100"],
        ["--active"],
        ["--region-id", "100", "--active", "--market-types"],
        ["--region-id", "100", "--industry-types", "--active"],
        ["--region-id", "100", "--type-id", "10", "--active"],
        ["--region-id", "100", "--type-id", "10", "--include", "2"],
        ["--region-id", "100", "--type-id", "10", "--exclude", "2"],
        ["--region-id", "100", "--active", "--batch-size", "0"],
        ["--region-id", "100", "--active", "--batch-size", "-1"],
        ["--region-id", "100", "--active", "--batch-size", "invalid"],
        ["--region-id", "100", "--active", "--failure-limit", "0"],
        ["--region-id", "100", "--active", "--failure-limit", "-1"],
        ["--region-id", "100", "--active", "--failure-limit", "invalid"],
        ["--region-id", "100", "--active", "--progress", "invalid"],
    ],
)
def test_argument_errors_precede_resources(
    environment: Environment, arguments: list[str]
) -> None:
    """Invalid combinations and execution controls fail before opening resources."""
    result = _invoke(environment, *arguments)
    assert result.exit_code == 2, result.output
    environment.manager.__aenter__.assert_not_awaited()
    environment.discovery.assert_not_awaited()
    environment.updater.assert_not_awaited()


@pytest.mark.parametrize("quiet", [False, True])
def test_industry_stub(environment: Environment, quiet: bool) -> None:
    """Industry accepts filters and controls but never masquerades as success."""
    result = _invoke(
        environment,
        "--hubs",
        "--industry-types",
        "--include",
        "2",
        "--exclude",
        "3",
        "--batch-size",
        "2",
        "--failure-limit",
        "3",
        *(["--quiet"] if quiet else []),
    )
    assert result.exit_code == 1, result.output
    assert "Industry type selection is not implemented yet" in result.output
    environment.manager.__aenter__.assert_not_awaited()
    environment.discovery.assert_not_awaited()
    environment.updater.assert_not_awaited()


@pytest.mark.parametrize(
    ("mode", "filters", "expected"),
    [
        ("--market-types", list[str](), {10, 12}),
        ("--market-types", ["--include", "2"], {10}),
        ("--market-types", ["--include", "2", "--include", "3"], {10, 12}),
        ("--market-types", ["--exclude", "2"], {12}),
        ("--market-types", ["--exclude", "2", "--include", "2"], set[int]()),
        ("--active", list[str](), {10, 12, 13, 99}),
        ("--active", ["--include", "1"], {10, 12}),
        ("--active", ["--include", "2", "--include", "3"], {10, 12}),
        ("--active", ["--exclude", "2"], {12, 13, 99}),
        ("--active", ["--include", "1", "--exclude", "2"], {12}),
        ("--active", ["--include", "2", "--exclude", "2"], set[int]()),
    ],
)
def test_selection_filters(
    environment: Environment, mode: str, filters: list[str], expected: set[int]
) -> None:
    """Filters intersect candidates, exclude unpublished IDs, and never add IDs."""
    environment.discovery.return_value = {10, 11, 12, 13, 99}
    result = _invoke(
        environment, "--region-id", "100", mode, *filters, "--progress", "plain"
    )
    assert result.exit_code == 0, result.output
    assert [
        call.kwargs["type_id"] for call in environment.updater.await_args_list
    ] == sorted(expected)
    if mode == "--active":
        assert "Warning:" in result.output
        assert "99" in result.output
    else:
        environment.discovery.assert_not_awaited()


def test_filters_cannot_expand_active_candidates(environment: Environment) -> None:
    """Included groups do not add statically listed but inactive types."""
    environment.discovery.return_value = {12}
    result = _invoke(environment, "--region-id", "100", "--active", "--include", "1")
    assert result.exit_code == 0, result.output
    assert [call.kwargs["type_id"] for call in environment.updater.await_args_list] == [
        12
    ]


@pytest.mark.parametrize("mode", ["--active", "--market-types"])
@pytest.mark.parametrize("invalid", ["region", "filter", "dataset"])
def test_static_validation_precedes_discovery(
    environment: Environment,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    invalid: str,
) -> None:
    """All required region/group data is checked before network requests."""
    if invalid == "dataset":
        monkeypatch.setattr(command.static_read, "market_groups", Mock(return_value={}))
    result = _invoke(
        environment,
        "--region-id",
        "999" if invalid == "region" else "100",
        mode,
        "--include",
        "999" if invalid == "filter" else "1",
    )
    assert result.exit_code == 2, result.output
    environment.discovery.assert_not_awaited()
    environment.updater.assert_not_awaited()


def test_explicit_ids_are_unrestricted_and_deduplicated(
    environment: Environment,
) -> None:
    """Explicit unpublished, nonmarket, and unknown types remain eligible."""
    result = _invoke(
        environment,
        "--region-id",
        "200",
        "--region-id",
        "100",
        "--region-id",
        "200",
        "--type-id",
        "99",
        "--type-id",
        "11",
        "--type-id",
        "13",
        "--type-id",
        "99",
    )
    assert result.exit_code == 0, result.output
    assert [
        (call.kwargs["region_id"], call.kwargs["type_id"])
        for call in environment.updater.await_args_list
    ] == [(region_id, type_id) for region_id in (200, 100) for type_id in (11, 13, 99)]


def test_hubs_append_in_order(environment: Environment) -> None:
    """Explicit regions precede hubs and overlapping selections run once."""
    first = MARKET_HUBS[-1].region_id
    result = _invoke(environment, "--region-id", str(first), "--hubs", "--market-types")
    assert result.exit_code == 0, result.output
    assert list(
        dict.fromkeys(
            call.kwargs["region_id"] for call in environment.updater.await_args_list
        )
    ) == list(dict.fromkeys([first, *(hub.region_id for hub in MARKET_HUBS)]))


@pytest.mark.parametrize("mode", ["--active", "--market-types", "--type-id"])
def test_independent_regional_failure_limits(
    environment: Environment, mode: str
) -> None:
    """An aborted region cleans up and does not consume the next region's budget."""
    environment.updater.return_value = UpdateResult(
        status=UpdateStatus.FAILED, previous_state=None, failure_message="HTTP failure"
    )
    selection = [mode, "10", "--type-id", "12"] if mode == "--type-id" else [mode]
    result = _invoke(
        environment,
        "--region-id",
        "200",
        "--region-id",
        "100",
        *selection,
        "--batch-size",
        "1",
        "--failure-limit",
        "1",
        "--quiet",
    )
    assert result.exit_code == 1, result.output
    assert [
        (call.kwargs["region_id"], call.kwargs["type_id"])
        for call in environment.updater.await_args_list
    ] == [(200, 10), (100, 10)]
    assert result.output.count("Aborted:") == 2
    assert result.output.count("regional limit of 1") == 2
    assert result.output.count("HTTP failure") == 2
    environment.manager.__aexit__.assert_awaited_once()


def test_discovery_failures_continue(environment: Environment) -> None:
    """Discovery errors are visible and later regions retain their own candidates."""
    environment.discovery.side_effect = [ValueError("discovery unavailable"), {12}]
    result = _invoke(
        environment, "--region-id", "200", "--region-id", "100", "--active"
    )
    assert result.exit_code == 1, result.output
    assert "discovery unavailable" in " ".join(result.output.split())
    assert "discovery_failed=1" in result.output
    assert [
        (call.kwargs["region_id"], call.kwargs["type_id"])
        for call in environment.updater.await_args_list
    ] == [(100, 12)]


def test_active_regions_are_isolated_and_sequential(environment: Environment) -> None:
    """A region's history completes before discovery for the next region begins."""
    events: list[tuple[str, int, int]] = []

    async def discover(*args: object, region_id: int) -> set[int]:
        events.append(("discover", region_id, 0))
        return {10} if region_id == 200 else {12}

    async def update(
        *args: object, region_id: int, type_id: int
    ) -> UpdateResult[object]:
        events.append(("start", region_id, type_id))
        await asyncio.sleep(0)
        events.append(("finish", region_id, type_id))
        return UpdateResult(status=UpdateStatus.SKIPPED, previous_state=None)

    environment.discovery.side_effect = discover
    environment.updater.side_effect = update
    result = _invoke(
        environment, "--region-id", "200", "--region-id", "100", "--active"
    )
    assert result.exit_code == 0, result.output
    assert events == [
        ("discover", 200, 0),
        ("start", 200, 10),
        ("finish", 200, 10),
        ("discover", 100, 0),
        ("start", 100, 12),
        ("finish", 100, 12),
    ]
    assert "Market history total: updated=0, skipped=2" in result.output


def test_batch_size_bounds_concurrency(environment: Environment) -> None:
    """The configured batch size bounds actual in-flight updates."""
    active = maximum = 0

    async def update(*args: object, **kwargs: int) -> UpdateResult[object]:
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0)
        active -= 1
        return UpdateResult(status=UpdateStatus.SKIPPED, previous_state=None)

    environment.updater.side_effect = update
    result = _invoke(environment, "--region-id", "100", "--active", "--batch-size", "2")
    assert result.exit_code == 0, result.output
    assert maximum == 2
    assert environment.updater.await_count == 4
    assert "Completed 2/4" in result.output
    assert "Completed 4/4" in result.output


def test_unfiltered_active_needs_no_market_groups(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Discovery can fetch unknown IDs without loading static market groups."""
    groups = Mock(side_effect=AssertionError("Market groups should not be read."))
    monkeypatch.setattr(command.static_read, "market_groups", groups)
    monkeypatch.setattr(command.static_read, "types", Mock(return_value={}))
    environment.discovery.return_value = {99}
    result = _invoke(environment, "--region-id", "100", "--active", "--quiet")
    assert result.exit_code == 0, result.output
    assert "Warning:" in result.output
    assert environment.updater.await_count == 1
    groups.assert_not_called()


def test_abort_cleanup_precedes_next_region(environment: Environment) -> None:
    """Cancelled work finishes cleanup before the next discovery and totals reconcile."""
    cleaned = False
    started: asyncio.Event | None = None

    async def discover(*args: object, region_id: int) -> set[int]:
        nonlocal started
        if region_id == 100:
            started = asyncio.Event()
        else:
            assert cleaned
        return {10, 12}

    async def update(
        *args: object, region_id: int, type_id: int
    ) -> UpdateResult[object]:
        nonlocal cleaned
        assert started is not None
        if region_id == 200:
            return UpdateResult(status=UpdateStatus.SKIPPED, previous_state=None)
        if type_id == 10:
            await started.wait()
            return UpdateResult(
                status=UpdateStatus.FAILED,
                previous_state=None,
                failure_message="regional failure",
            )
        try:
            started.set()
            await asyncio.Event().wait()
            raise AssertionError("Pending update should be cancelled.")
        finally:
            await asyncio.sleep(0)
            cleaned = True

    environment.discovery.side_effect = discover
    environment.updater.side_effect = update
    result = _invoke(
        environment,
        "--region-id",
        "100",
        "--region-id",
        "200",
        "--active",
        "--batch-size",
        "2",
        "--failure-limit",
        "1",
    )
    assert result.exit_code == 1, result.output
    assert cleaned
    assert (
        "Market history total: updated=0, skipped=2, failed=1, "
        "cancelled=1, not_started=0."
    ) in " ".join(result.output.split())
    environment.manager.__aexit__.assert_awaited_once()


def test_default_limits_and_plain_intervals(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Omitted controls resolve shared constants, including plain reporting cadence."""
    monkeypatch.setattr(bulk, "MARKET_HISTORY_BATCH_SIZE", 2)
    monkeypatch.setattr(bulk, "MARKET_HISTORY_FAILURE_LIMIT", 1)
    runner = AsyncMock(wraps=bulk.update_market_histories)
    monkeypatch.setattr(bulk, "update_market_histories", runner)
    result = _invoke(
        environment, "--region-id", "100", "--active", "--progress", "plain"
    )
    assert result.exit_code == 0, result.output
    assert runner.await_args is not None
    assert runner.await_args.kwargs["batch_size"] == bulk.MARKET_HISTORY_BATCH_SIZE
    assert (
        runner.await_args.kwargs["failure_limit"] == bulk.MARKET_HISTORY_FAILURE_LIMIT
    )
    assert "Completed 2/4" in result.output
    assert "Completed 4/4" in result.output


@pytest.mark.parametrize(
    ("style", "quiet", "disabled"),
    [
        ("auto", False, True),
        ("plain", False, True),
        ("live", False, False),
        ("live", True, True),
    ],
)
def test_progress_styles_and_cleanup(
    environment: Environment,
    monkeypatch: pytest.MonkeyPatch,
    style: str,
    quiet: bool,
    disabled: bool,
) -> None:
    """Progress uses the requested style and always exits its context."""
    instances: list[Progress] = []

    def make_progress(
        *columns: str | ProgressColumn,
        console: Console,
        disable: bool,
        transient: bool,
    ) -> Progress:
        assert not console.is_terminal
        progress = Progress(
            *columns,
            console=Console(file=StringIO(), force_terminal=False),
            disable=disable,
            transient=transient,
        )
        instances.append(progress)
        return progress

    monkeypatch.setattr(command, "Progress", make_progress)
    result = _invoke(
        environment,
        "--region-id",
        "100",
        "--market-types",
        "--progress",
        style,
        *(["--quiet"] if quiet else []),
    )
    assert result.exit_code == 0, result.output
    assert len(instances) == 1
    assert instances[0].disable is disabled
    assert not instances[0].live.is_started
    assert instances[0].tasks[0].completed == 2
    if quiet:
        assert result.output == ""


def test_abort_totals_leave_progress_incomplete(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not-started pairs remain visible instead of appearing successfully completed."""
    progress = Progress(console=Console(file=StringIO()), disable=True)
    monkeypatch.setattr(command, "Progress", Mock(return_value=progress))
    environment.updater.return_value = UpdateResult(
        status=UpdateStatus.FAILED, previous_state=None, failure_message="failure"
    )
    result = _invoke(
        environment,
        "--region-id",
        "100",
        "--market-types",
        "--batch-size",
        "1",
        "--failure-limit",
        "1",
        "--progress",
        "live",
    )
    assert result.exit_code == 1, result.output
    assert "failed=1, cancelled=0, not_started=1" in " ".join(result.output.split())
    assert progress.tasks[0].completed == 1
    assert progress.tasks[0].total == 2
    assert not progress.live.is_started


def test_interruption_awaits_cleanup_and_stops_regions(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """External cancellation closes resources without starting another region."""
    events: list[str] = []

    progress = Progress(console=Console(file=StringIO()), disable=True)
    monkeypatch.setattr(command, "Progress", Mock(return_value=progress))

    async def interrupt() -> None:
        parent = asyncio.current_task()
        assert parent is not None

        async def update(*args: object, **kwargs: int) -> UpdateResult[object]:
            try:
                asyncio.get_running_loop().call_soon(parent.cancel)
                await asyncio.Event().wait()
                raise AssertionError("Update should have been cancelled.")
            finally:
                await asyncio.sleep(0)
                events.append("cleaned")

        environment.updater.side_effect = update
        with pytest.raises(asyncio.CancelledError):
            await command._fetch_market_history(  # pyright: ignore[reportPrivateUsage]
                settings=environment.settings,
                options=command.HistoryFetchOptions(
                    region_ids=[100, 200],
                    type_ids=set(),
                    selection=command.SelectionMode.ACTIVE,
                    include=set(),
                    exclude=set(),
                    batch_size=4,
                    failure_limit=2,
                    progress=command.ProgressStyle.LIVE,
                    quiet=False,
                ),
            )

    asyncio.run(interrupt())
    assert events == ["cleaned"] * 4
    assert environment.discovery.await_count == 1
    environment.manager.__aexit__.assert_awaited_once()
    assert not progress.live.is_started
