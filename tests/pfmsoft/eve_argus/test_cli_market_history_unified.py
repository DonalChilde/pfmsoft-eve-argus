"""Tests for unified history selection, regional execution, and output."""

import asyncio
import json
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Literal
from unittest.mock import AsyncMock, Mock

import pytest
from pfmsoft.eve_link import EsiRequest, EsiResponse, FailedEsiResponse
from rich.console import Console
from rich.progress import Progress, ProgressColumn
from typer.testing import CliRunner, Result

from pfmsoft.eve_argus.cli import app
from pfmsoft.eve_argus.cli.fetch import market_history as command
from pfmsoft.eve_argus.cli.fetch._market_history_selection import active_type_ids
from pfmsoft.eve_argus.fetch_esi import market_history_bulk as bulk
from pfmsoft.eve_argus.fetch_esi.update import UpdateResult, UpdateStatus
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings
from pfmsoft.eve_argus.static import models as ASM
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
    blueprints = {
        10: ASM.BlueprintRecord(
            blueprint_type_id=10,
            activities=ASM.BlueprintActivities(
                manufacturing=ASM.Blueprint_Activity(
                    time=60,
                    materials=(
                        ASM.Blueprint_Material(type_id=11, quantity=1),
                        ASM.Blueprint_Material(type_id=13, quantity=1),
                        ASM.Blueprint_Material(type_id=99, quantity=1),
                    ),
                    products=(ASM.Blueprint_Product(type_id=10, quantity=1),),
                    skills=(ASM.Blueprint_Skill(type_id=12, level=1),),
                )
            ),
        )
    }
    monkeypatch.setattr(
        command.static_read, "blueprints", Mock(return_value=blueprints)
    )
    monkeypatch.setattr(
        command.static_read,
        "type_materials",
        Mock(
            return_value={
                10: ASM.TypeMaterialsRecord(
                    type_id=10,
                    materials=tuple(
                        ASM.Materials(material_type_id=type_id, quantity=1)
                        for type_id in (11, 12, 13, 99)
                    ),
                ),
            }
        ),
    )
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
        "--from",
        "--active",
        "--market-types",
        "--industry-types",
        "--scrapmetal",
        "--include",
        "--exclude",
        "--workers",
        "--failure-limit",
        "--progress",
        "--quiet",
    ):
        assert option in result.output
    assert "--all-market-types" not in result.output
    assert "--all-industry-types" not in result.output
    assert "--batch-size" not in result.output
    environment.manager.__aenter__.assert_not_awaited()


@pytest.mark.parametrize(
    "name",
    ["market-history-active", "market-history-bulk", "market-history-bulk-progress"],
)
def test_obsolete_commands_are_removed(environment: Environment, name: str) -> None:
    """Old names are absent from help and rejected rather than aliased."""
    runner = CliRunner()
    context = {SETTINGS_KEY: environment.settings}
    help_result = runner.invoke(app, ["fetch", "--help"], obj=context)
    assert help_result.exit_code == 0, help_result.output
    assert "market-history" in help_result.output
    assert name not in help_result.output
    result = runner.invoke(app, ["fetch", name, "--help"], obj=context)
    assert result.exit_code == 2, result.output
    assert "No such command" in result.output
    environment.manager.__aenter__.assert_not_awaited()


@pytest.mark.parametrize("failure", ["response", "blank", "malformed", "exception"])
@pytest.mark.parametrize("quiet", [False, True])
def test_real_discovery_failures_continue(
    environment: Environment,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    quiet: bool,
) -> None:
    """Real discovery validates ESI failures and continues to later regions."""
    response = Mock(spec=EsiResponse)
    response.esi_request = EsiRequest(
        operation_id="GetMarketsRegionIdTypes", path_parameters={"region_id": 100}
    )
    response.response_data = ["not-an-id"]
    failed = Mock(spec=FailedEsiResponse)
    failed.failed_response.error_messages = (
        [" ", "discovery broke"] if failure == "response" else [" "]
    )
    success = Mock(spec=EsiResponse)
    success.esi_request = EsiRequest(
        operation_id="GetMarketsRegionIdTypes", path_parameters={"region_id": 200}
    )
    success.response.metadata.received_at = "2026-10-21T00:00:00Z"
    success.response.metadata.expires_at_instant = None
    success.response_data = [12, 12]
    first = (
        RuntimeError("discovery broke")
        if failure == "exception"
        else response
        if failure == "malformed"
        else failed
    )
    environment.resources.esi_link.make_request = AsyncMock(
        side_effect=[first, success]
    )
    monkeypatch.setattr(command, "active_type_ids", active_type_ids)
    result = _invoke(
        environment,
        "--region-id",
        "100",
        "--region-id",
        "200",
        "--active",
        *(["--quiet"] if quiet else []),
    )
    assert result.exit_code == 1, result.output
    message = (
        "without an error reason"
        if failure == "blank"
        else "GetMarketsRegionIdTypes"
        if failure == "malformed"
        else "discovery broke"
    )
    assert message in " ".join(result.output.replace("│", " ").split())
    assert [
        (call.kwargs["region_id"], call.kwargs["type_id"])
        for call in environment.updater.await_args_list
    ] == [(200, 12)]
    environment.manager.__aexit__.assert_awaited_once()


@pytest.mark.parametrize("empty_ids", [set[int](), {11}])
def test_empty_active_region_continues(
    environment: Environment, empty_ids: set[int]
) -> None:
    """Empty or entirely unpublished candidates do not stop later regions."""
    environment.discovery.side_effect = [empty_ids, {12}]
    result = _invoke(
        environment, "--region-id", "100", "--region-id", "200", "--active"
    )
    assert result.exit_code == 0, result.output
    assert "No market types selected" in result.output
    assert environment.updater.await_count == 1
    assert environment.updater.await_args is not None
    assert environment.updater.await_args.kwargs["region_id"] == 200


@pytest.mark.parametrize("damage", ["types", "path", "reference", "group"])
def test_corrupt_static_selection_prevents_updates(
    environment: Environment,
    monkeypatch: pytest.MonkeyPatch,
    damage: Literal["types", "path", "reference", "group"],
) -> None:
    """Missing datasets and inconsistent published-type paths fail explicitly."""
    match damage:
        case "types":
            monkeypatch.setattr(command.static_read, "types", Mock(return_value={}))
        case "path":
            groups = command.static_read.market_groups(
                environment.resources.argus_static_db_connection
            )
            groups[2].int_path = (999, 2)
        case "reference":
            environment.types[10].market_group_id = 3
        case "group":
            environment.types[10].market_group_id = 999
    result = _invoke(environment, "--region-id", "100", "--market-types", "--quiet")
    assert result.exit_code == 2, result.output
    assert result.output
    environment.updater.assert_not_awaited()


def test_below_limit_failures_do_not_accumulate_across_regions(
    environment: Environment,
) -> None:
    """Below-limit failures permit remaining pairs and reset for the next region."""
    environment.updater.side_effect = [
        UpdateResult(
            status=UpdateStatus.FAILED, previous_state=None, failure_message="bad"
        ),
        UpdateResult(status=UpdateStatus.UPDATED, previous_state=None),
        RuntimeError("updater broke"),
        UpdateResult(status=UpdateStatus.SKIPPED, previous_state=None),
    ]
    result = _invoke(
        environment,
        "--region-id",
        "100",
        "--region-id",
        "200",
        "--market-types",
        "--workers",
        "1",
        "--failure-limit",
        "2",
    )
    assert result.exit_code == 1, result.output
    assert environment.updater.await_count == 4
    output = " ".join(result.output.split())
    assert "RuntimeError: updater broke" in output
    assert "Aborted" not in output
    assert "Market history total: updated=1, skipped=1, failed=2" in output


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--region-id", "100"],
        ["--active"],
        ["--region-id", "100", "--active", "--market-types"],
        ["--region-id", "100", "--industry-types", "--active"],
        ["--region-id", "100", "--scrapmetal", "--active"],
        ["--region-id", "100", "--scrapmetal", "--market-types"],
        ["--region-id", "100", "--scrapmetal", "--industry-types"],
        ["--region-id", "100", "--scrapmetal", "--type-id", "10"],
        ["--region-id", "100", "--type-id", "10", "--active"],
        ["--region-id", "100", "--type-id", "10", "--include", "2"],
        ["--region-id", "100", "--type-id", "10", "--exclude", "2"],
        ["--region-id", "100", "--active", "--workers", "0"],
        ["--region-id", "100", "--active", "--workers", "-1"],
        ["--region-id", "100", "--active", "--workers", "invalid"],
        ["--region-id", "100", "--active", "--batch-size", "2"],
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
def test_industry_selection(environment: Environment, quiet: bool) -> None:
    """Industry fetches deduplicated blueprint/material/product IDs, excluding skills."""
    result = _invoke(
        environment,
        "--region-id",
        "200",
        "--region-id",
        "100",
        "--industry-types",
        "--workers",
        "2",
        "--failure-limit",
        "3",
        *(["--quiet"] if quiet else []),
    )
    assert result.exit_code == 0, result.output
    assert [
        (call.kwargs["region_id"], call.kwargs["type_id"])
        for call in environment.updater.await_args_list
    ] == [(region, 10) for region in (200, 100)]
    assert "Warning:" in result.output
    assert "99" in result.output
    if quiet:
        assert "selected" not in result.output
    environment.manager.__aexit__.assert_awaited_once()
    environment.discovery.assert_not_awaited()


def test_industry_requires_blueprints(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing blueprint data fails explicitly before history requests."""
    monkeypatch.setattr(command.static_read, "blueprints", Mock(return_value={}))
    result = _invoke(environment, "--region-id", "100", "--industry-types", "--quiet")
    assert result.exit_code == 2, result.output
    assert "blueprints" in result.output
    environment.updater.assert_not_awaited()


def test_industry_combines_all_blueprints(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Combine multiple blueprints and include non-manufacturing products once."""
    blueprints = command.static_read.blueprints(
        environment.resources.argus_static_db_connection
    )
    blueprints[13] = ASM.BlueprintRecord(
        blueprint_type_id=13,
        activities=ASM.BlueprintActivities(
            invention=ASM.Blueprint_Activity(
                time=60,
                materials=(ASM.Blueprint_Material(type_id=10, quantity=1),),
                products=(ASM.Blueprint_Product(type_id=12, quantity=1),),
            )
        ),
    )
    reader = Mock(return_value=blueprints)
    monkeypatch.setattr(command.static_read, "blueprints", reader)
    result = _invoke(
        environment, "--region-id", "100", "--region-id", "200", "--industry-types"
    )
    assert result.exit_code == 0, result.output
    assert [
        (call.kwargs["region_id"], call.kwargs["type_id"])
        for call in environment.updater.await_args_list
    ] == [(region, type_id) for region in (100, 200) for type_id in (10, 12)]
    reader.assert_called_once_with(environment.resources.argus_static_db_connection)


def test_industry_all_unpublished_is_noop(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A populated blueprint dataset can yield a successful empty selection."""
    monkeypatch.setattr(
        command.static_read,
        "blueprints",
        Mock(
            return_value={
                11: ASM.BlueprintRecord(
                    blueprint_type_id=11, activities=ASM.BlueprintActivities()
                )
            }
        ),
    )
    result = _invoke(environment, "--region-id", "100", "--industry-types")
    assert result.exit_code == 0, result.output
    assert "No market types selected" in result.output
    environment.updater.assert_not_awaited()


def test_industry_without_groups_or_known_types(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without known type records no industry IDs have proven market membership."""
    monkeypatch.setattr(command.static_read, "types", Mock(return_value={}))
    groups = Mock(side_effect=AssertionError("Market groups must not be read"))
    monkeypatch.setattr(command.static_read, "market_groups", groups)
    result = _invoke(environment, "--region-id", "100", "--industry-types", "--quiet")
    assert result.exit_code == 0, result.output
    environment.updater.assert_not_awaited()
    assert "Warning:" in result.output
    groups.assert_not_called()


def test_industry_excludes_nonmarket_blueprints(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Blueprints without market groups cannot bypass a group-2 exclusion."""
    monkeypatch.setattr(
        command.static_read,
        "blueprints",
        Mock(
            return_value={
                13: ASM.BlueprintRecord(
                    blueprint_type_id=13,
                    activities=ASM.BlueprintActivities(
                        manufacturing=ASM.Blueprint_Activity(
                            time=60,
                            materials=(ASM.Blueprint_Material(type_id=10, quantity=1),),
                            products=(ASM.Blueprint_Product(type_id=12, quantity=1),),
                        )
                    ),
                )
            }
        ),
    )
    result = _invoke(
        environment, "--region-id", "100", "--industry-types", "--exclude", "2"
    )
    assert result.exit_code == 0, result.output
    assert [call.kwargs["type_id"] for call in environment.updater.await_args_list] == [
        12
    ]
    assert "excluded 1 nonmarket" in " ".join(result.output.split())


@pytest.mark.parametrize("mode", ["--active", "--industry-types"])
def test_market_membership_uses_types_without_loading_groups(
    environment: Environment, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """Unfiltered generated selections use type records to prove market membership."""
    groups = Mock(side_effect=AssertionError("Market groups must not be read"))
    monkeypatch.setattr(command.static_read, "market_groups", groups)
    result = _invoke(environment, "--region-id", "100", mode)
    assert result.exit_code == 0, result.output
    expected = [10, 12] if mode == "--active" else [10]
    assert [
        call.kwargs["type_id"] for call in environment.updater.await_args_list
    ] == expected
    groups.assert_not_called()


@pytest.mark.parametrize(
    ("mode", "filters", "expected"),
    [
        ("--market-types", list[str](), {10, 12}),
        ("--market-types", ["--include", "2"], {10}),
        ("--market-types", ["--include", "2", "--include", "3"], {10, 12}),
        ("--market-types", ["--exclude", "2"], {12}),
        ("--market-types", ["--exclude", "2", "--include", "2"], set[int]()),
        ("--active", list[str](), {10, 12}),
        ("--active", ["--include", "1"], {10, 12}),
        ("--active", ["--include", "2", "--include", "3"], {10, 12}),
        ("--active", ["--exclude", "2"], {12}),
        ("--active", ["--include", "1", "--exclude", "2"], {12}),
        ("--active", ["--include", "2", "--exclude", "2"], set[int]()),
        ("--industry-types", list[str](), {10}),
        ("--industry-types", ["--include", "1"], {10}),
        ("--industry-types", ["--exclude", "2"], set[int]()),
        ("--industry-types", ["--include", "2", "--include", "3"], {10}),
        ("--industry-types", ["--include", "2", "--exclude", "2"], set[int]()),
        ("--scrapmetal", list[str](), {10, 12}),
        ("--scrapmetal", ["--include", "2"], {10}),
        ("--scrapmetal", ["--include", "2", "--include", "3"], {10, 12}),
        ("--scrapmetal", ["--exclude", "2"], {12}),
        ("--scrapmetal", ["--include", "2", "--exclude", "2"], set[int]()),
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


@pytest.mark.parametrize(
    "mode", ["--active", "--market-types", "--industry-types", "--scrapmetal"]
)
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


def test_scrapmetal_requires_materials(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing material data fails before any history requests."""
    monkeypatch.setattr(command.static_read, "type_materials", Mock(return_value={}))
    result = _invoke(environment, "--region-id", "100", "--scrapmetal", "--quiet")
    assert result.exit_code == 2, result.output
    assert "Static type materials dataset must be populated" in result.output
    environment.updater.assert_not_awaited()


def test_scrapmetal_candidates_apply_to_all_regions(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Market-listed non-material types are excluded even without group filters."""
    materials = Mock(
        return_value={
            10: ASM.TypeMaterialsRecord(type_id=10, materials=()),
        }
    )
    monkeypatch.setattr(command.static_read, "type_materials", materials)
    result = _invoke(
        environment, "--region-id", "100", "--region-id", "200", "--scrapmetal"
    )
    assert result.exit_code == 0, result.output
    assert [
        (call.kwargs["region_id"], call.kwargs["type_id"])
        for call in environment.updater.await_args_list
    ] == [(100, 10), (200, 10)]
    materials.assert_called_once_with(environment.resources.argus_static_db_connection)
    environment.discovery.assert_not_awaited()


def test_scrapmetal_without_eligible_types_is_noop(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unpublished, nonmarket, and unknown material IDs do not trigger requests."""
    monkeypatch.setattr(
        command.static_read,
        "type_materials",
        Mock(
            return_value={
                11: ASM.TypeMaterialsRecord(
                    type_id=11,
                    materials=(
                        ASM.Materials(material_type_id=13, quantity=1),
                        ASM.Materials(material_type_id=99, quantity=1),
                    ),
                ),
            }
        ),
    )
    result = _invoke(environment, "--region-id", "100", "--scrapmetal")
    assert result.exit_code == 0, result.output
    assert "selected 0 types" in result.output
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


@pytest.mark.parametrize(
    "mode", ["--active", "--market-types", "--industry-types", "--type-id"]
)
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
        "--workers",
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


def test_worker_count_bounds_concurrency(environment: Environment) -> None:
    """The configured worker count bounds actual in-flight updates."""
    active = maximum = 0

    async def update(*args: object, **kwargs: int) -> UpdateResult[object]:
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0)
        active -= 1
        return UpdateResult(status=UpdateStatus.SKIPPED, previous_state=None)

    environment.updater.side_effect = update
    result = _invoke(environment, "--region-id", "100", "--active", "--workers", "2")
    assert result.exit_code == 0, result.output
    assert maximum == 2
    assert environment.updater.await_count == 2
    assert "Completed 2/2" in result.output
    assert "workers 2" in " ".join(result.output.split())


def test_unfiltered_active_needs_no_market_groups(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unknown active IDs warn but never fetch; market groups need not be loaded."""
    groups = Mock(side_effect=AssertionError("Market groups should not be read."))
    monkeypatch.setattr(command.static_read, "market_groups", groups)
    monkeypatch.setattr(command.static_read, "types", Mock(return_value={}))
    environment.discovery.return_value = {99}
    result = _invoke(environment, "--region-id", "100", "--active", "--quiet")
    assert result.exit_code == 0, result.output
    assert "Warning:" in result.output
    environment.updater.assert_not_awaited()
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
        "--workers",
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
    monkeypatch.setattr(bulk, "MARKET_HISTORY_WORKER_COUNT", 2)
    monkeypatch.setattr(bulk, "MARKET_HISTORY_FAILURE_LIMIT", 1)
    runner = AsyncMock(wraps=bulk.update_market_histories)
    monkeypatch.setattr(bulk, "update_market_histories", runner)
    result = _invoke(
        environment, "--region-id", "100", "--active", "--progress", "plain"
    )
    assert result.exit_code == 0, result.output
    assert runner.await_args is not None
    assert runner.await_args.kwargs["worker_count"] == bulk.MARKET_HISTORY_WORKER_COUNT
    assert (
        runner.await_args.kwargs["failure_limit"] == bulk.MARKET_HISTORY_FAILURE_LIMIT
    )
    assert "Completed 2/2" in result.output


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
        "--workers",
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
                    worker_count=4,
                    failure_limit=2,
                    progress=command.ProgressStyle.LIVE,
                    quiet=False,
                ),
            )

    asyncio.run(interrupt())
    assert events == ["cleaned"] * 2
    assert environment.discovery.await_count == 1
    environment.manager.__aexit__.assert_awaited_once()
    assert not progress.live.is_started


def _selection_file(tmp_path: Path, content: object) -> Path:
    path = tmp_path / "selection.json"
    path.write_text(content if isinstance(content, str) else json.dumps(content))
    return path


def test_from_file_selects_regions_and_types(
    environment: Environment, tmp_path: Path
) -> None:
    """File regions follow explicit regions, precede hubs, and use file types."""
    path = _selection_file(tmp_path, {"region_ids": [200, 100], "type_ids": [12, 10]})
    hub = MARKET_HUBS[0].region_id
    result = _invoke(environment, "--region-id", "100", "--from", str(path), "--hubs")
    assert result.exit_code == 0, result.output
    pairs = [
        (call.kwargs["region_id"], call.kwargs["type_id"])
        for call in environment.updater.await_args_list
    ]
    regions = list(dict.fromkeys([100, 200, *(h.region_id for h in MARKET_HUBS)]))
    assert list(dict.fromkeys(region for region, _ in pairs)) == regions
    assert sorted(type_id for region, type_id in pairs if region == hub) == [10, 12]
    environment.discovery.assert_not_awaited()


@pytest.mark.parametrize(
    ("type_ids", "message"),
    [
        ([10, 11], "unpublished type IDs: [11]"),
        ([10, 13], "nonmarket type IDs: [13]"),
        ([10, 99], "unknown type IDs: [99]"),
    ],
)
def test_from_file_invalid_types_fail_before_updates(
    environment: Environment, tmp_path: Path, type_ids: list[int], message: str
) -> None:
    """File types must be published, market-listed static types."""
    path = _selection_file(tmp_path, {"region_ids": [100], "type_ids": type_ids})
    result = _invoke(environment, "--from", str(path))
    assert result.exit_code == 2, result.output
    assert message in " ".join(result.output.replace("│", " ").split())
    environment.updater.assert_not_awaited()


def test_from_file_unknown_regions_fail(
    environment: Environment, tmp_path: Path
) -> None:
    """File regions must exist in the static database, even for one pair."""
    path = _selection_file(tmp_path, {"region_ids": [7], "type_ids": [10]})
    result = _invoke(environment, "--from", str(path))
    assert result.exit_code == 2, result.output
    assert "Unknown region IDs" in result.output
    environment.updater.assert_not_awaited()


@pytest.mark.parametrize(
    ("content", "arguments"),
    [
        ({"region_ids": [100]}, []),
        ({"region_ids": [100], "type_ids": []}, []),
        ("{bad", []),
        ({"region_ids": [100], "type_ids": [10]}, ["--type-id", "10"]),
        ({"region_ids": [100], "type_ids": [10]}, ["--active"]),
        ({"region_ids": [100], "type_ids": [10]}, ["--market-types"]),
        ({"region_ids": [100], "type_ids": [10]}, ["--scrapmetal"]),
        ({"region_ids": [100], "type_ids": [10]}, ["--include", "2"]),
        ({"region_ids": [100], "type_ids": [10]}, ["--exclude", "2"]),
    ],
)
def test_from_file_argument_errors_precede_resources(
    environment: Environment,
    tmp_path: Path,
    content: object,
    arguments: list[str],
) -> None:
    """Malformed files and conflicting selections fail before opening resources."""
    path = _selection_file(tmp_path, content)
    result = _invoke(environment, "--from", str(path), *arguments)
    assert result.exit_code == 2, result.output
    environment.manager.__aenter__.assert_not_awaited()
    environment.updater.assert_not_awaited()
