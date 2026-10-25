"""Corporation blueprint collection, rendering, and CLI regression tests."""

import asyncio
import csv
import json
import re
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass, fields, replace
from io import StringIO
from pathlib import Path
from typing import Literal
from unittest.mock import AsyncMock, Mock

import pytest
from pfmsoft.eve_link import EsiLink, EsiResponse, EsiSchema, FailedEsiResponse
from typer.testing import CliRunner
from whenever import Instant

from pfmsoft.eve_argus.dynamic.models import (
    CorporationBlueprintRecord,
    CorporationBlueprintsDataset,
)
from pfmsoft.eve_argus.esi import fetch
from pfmsoft.eve_argus.reports.corp_blueprints import (
    CorporationBlueprintsReport,
    classify_blueprint_quantity,
    collect_corporation_blueprints_report,
    collect_universe_name_ids,
)
from pfmsoft.eve_argus.reports.corp_blueprints_render import (
    render_corporation_blueprints_json,
    render_corporation_blueprints_markdown,
    render_missing_bpo_csv,
    render_owned_blueprints_csv,
)
from pfmsoft.eve_argus.static.models import MarketGroupsRecord, TypesRecord


@dataclass(slots=True, kw_only=True)
class Inputs:
    """In-memory source data and mocked ESI names for repeatable reports."""

    blueprints: CorporationBlueprintsDataset
    types: dict[int, TypesRecord]
    groups: dict[int, MarketGroupsRecord]
    names: AsyncMock


@pytest.fixture
def inputs(monkeypatch: pytest.MonkeyPatch) -> Inputs:
    """Include stacks, originals, copy-only ownership, and out-of-universe types."""
    blueprint = CorporationBlueprintRecord(
        corporation_id=98000001,
        item_id=1000000000001,
        type_id=100,
        location_id=60009454,
        location_flag="CorpSAG1",
        quantity=-1,
        material_efficiency=10,
        time_efficiency=12,
        runs=-1,
        response_metadata_id=1,
    )
    records = [
        blueprint,
        replace(
            blueprint,
            item_id=blueprint.item_id + 1,
            quantity=3,
            material_efficiency=9,
            time_efficiency=20,
        ),
        replace(
            blueprint,
            item_id=blueprint.item_id + 2,
            type_id=101,
            quantity=-2,
            runs=7,
            location_id=1040000000001,
        ),
        replace(
            blueprint, item_id=blueprint.item_id + 3, type_id=102, location_id=2004
        ),
    ]
    type_record = TypesRecord(
        type_id=100,
        name="Blueprint | A\nname",
        market_group_id=20,
        base_price=123.45,
        capacity=None,
        description=None,
        faction_id=None,
        graphic_id=None,
        category_id=9,
        group_id=1,
        icon_id=None,
        is_dynamic_type=None,
        is_repackable=None,
        mass=None,
        meta_group_id=None,
        meta_level=None,
        packaged_volume=None,
        portion_size=1,
        published=True,
        race_id=None,
        radius=None,
        ship_tree_group_id=None,
        sound_id=None,
        tech_level=None,
        variation_parent_type_id=None,
        volume=None,
    )
    group = MarketGroupsRecord(
        market_group_id=2,
        name="Blueprints",
        description="",
        has_types=False,
        icon_id=None,
        parent_group_id=None,
        int_path=(2,),
        str_path=("Blueprints",),
        types=(),
    )
    response = Mock(spec=EsiResponse)
    response.response_data = [
        {"id": 98000001, "name": "Example Corp", "category": "corporation"},
        {"id": 60009454, "name": "Station | A", "category": "station"},
    ]
    response.response.metadata.received_at = "2026-10-18T00:00:00Z"
    response.response.metadata.expires_at_instant = None
    names = AsyncMock(return_value=[response])
    monkeypatch.setattr(fetch, "universe_names", names)
    return Inputs(
        blueprints=CorporationBlueprintsDataset(
            corporation_id=98000001,
            response_metadata_id=1,
            received_at="2026-10-17T22:07:58.349474424Z",
            expires_at="2026-10-17T23:00:00Z",
            argus_expires_at=None,
            records={row.item_id: row for row in reversed(records)},
        ),
        types={
            100: type_record,
            101: replace(type_record, type_id=101, name="Copy only", base_price=None),
            102: replace(
                type_record,
                type_id=102,
                name="Unpublished",
                published=False,
                market_group_id=None,
            ),
            103: replace(type_record, type_id=103, name="Missing"),
        },
        groups={
            2: group,
            20: replace(
                group,
                market_group_id=20,
                parent_group_id=2,
                name="Components",
                int_path=(2, 20),
                str_path=("Blueprints", "Components"),
                has_types=True,
                types=(100, 101, 103),
            ),
        },
        names=names,
    )


def collect(inputs: Inputs) -> CorporationBlueprintsReport:
    """Collect a report using a fixed clock and mocked network dependencies."""
    return asyncio.run(
        collect_corporation_blueprints_report(
            blueprints=inputs.blueprints,
            types=inputs.types,
            market_groups=inputs.groups,
            esi_link=Mock(spec=EsiLink),
            schema=Mock(spec=EsiSchema),
            generated_at=Instant.parse_iso("2026-10-18T00:00:00Z"),
        )
    )


@pytest.mark.parametrize(
    "quantity,kind,count",
    [
        (-1, "original", 1),
        (-2, "copy", 1),
        (1, "stack", 1),
        (5, "stack", 5),
    ],
)
def test_quantity_classification(quantity: int, kind: str, count: int) -> None:
    """Sentinels classify items without interpreting copy runs as copy counts."""
    assert classify_blueprint_quantity(quantity) == (kind, count)


@pytest.mark.parametrize("quantity", [0, -3, -100])
def test_invalid_quantity(quantity: int) -> None:
    """Unknown quantities cannot silently reduce or inflate original counts."""
    with pytest.raises(ValueError, match="quantity"):
        classify_blueprint_quantity(quantity)


def test_complete_collection(inputs: Inputs) -> None:
    """All source rows survive; copy-only types remain missing originals."""
    report = collect(inputs)
    assert len(report.inventory) == 4
    assert [row.item_id for row in report.inventory] == sorted(
        inputs.blueprints.records
    )
    for row in report.inventory:
        for field in fields(CorporationBlueprintRecord):
            assert getattr(row, field.name) == getattr(
                inputs.blueprints.records[row.item_id], field.name
            )
    owned = {row.type_id: row for row in report.owned_bpos}
    assert owned[100].quantity == 4
    assert (owned[100].material_efficiency, owned[100].time_efficiency) == (10, 12)
    assert owned[100].selected_item_id == 1000000000001
    assert owned[102].in_comparison_universe is False
    assert {row.type_id for row in report.missing_bpos} == {101, 103}
    assert report.inventory[2].blueprint_kind == "copy"
    assert report.inventory[2].item_count == 1
    assert report.inventory[2].runs == 7
    assert report.inventory[2].location_name == "UNKNOWN"
    assert report.inventory[3].location_name == "UNKNOWN"
    assert report.inventory[0].location_name == "Station | A"
    assert report.is_stale is True
    assert report.corporation_name == "Example Corp"
    inputs.names.assert_awaited_once()
    assert inputs.names.call_args.kwargs["ids"] == {98000001, 60009454}


@pytest.mark.parametrize(
    "location", [2004, 30000001, 59999999, 64000000, 2**31, 1040000000001]
)
def test_lookup_excludes_nonstation_namespaces(inputs: Inputs, location: int) -> None:
    """Only the station ID namespace is eligible for location resolution."""
    base = next(iter(inputs.blueprints.records.values()))
    row = replace(base, location_id=location)
    data = replace(inputs.blueprints, records={row.item_id: row})
    assert collect_universe_name_ids(data) == {98000001}


@pytest.mark.parametrize("location", [60000000, 63999999])
def test_station_candidate_boundaries(inputs: Inputs, location: int) -> None:
    """Station range boundaries remain candidates, subject to response validation."""
    base = next(iter(inputs.blueprints.records.values()))
    row = replace(base, location_id=location)
    assert collect_universe_name_ids(
        replace(inputs.blueprints, records={row.item_id: row})
    ) == {98000001, location}


def test_mismatched_static_key_is_explicit(inputs: Inputs) -> None:
    """Incorrect type keys cannot create a false comparison universe."""
    inputs.types[100] = replace(inputs.types[100], type_id=999)
    with pytest.raises(ValueError, match="key 100"):
        collect(inputs)
    inputs.names.assert_not_awaited()


def test_empty_inventory_has_full_missing_set(inputs: Inputs) -> None:
    """An empty snapshot never falls back to older inventory or loses missing types."""
    inputs.blueprints = replace(inputs.blueprints, records={})
    report = collect(inputs)
    assert report.inventory == report.owned_bpos == ()
    assert {row.type_id for row in report.missing_bpos} == {100, 101, 103}


@pytest.mark.parametrize(
    "problem",
    [
        "quantity",
        "type",
        "group",
        "root",
        "corporation",
        "response",
        "record_key",
    ],
)
def test_invalid_source_fails_before_network(
    inputs: Inputs,
    problem: Literal[
        "quantity", "type", "group", "root", "corporation", "response", "record_key"
    ],
) -> None:
    """Static/source inconsistencies fail explicitly without requesting names."""
    row = next(iter(inputs.blueprints.records.values()))
    match problem:
        case "quantity":
            row = replace(row, quantity=0)
        case "type":
            row = replace(row, type_id=999)
        case "group":
            inputs.types[100] = replace(inputs.types[100], market_group_id=999)
        case "root":
            inputs.groups.pop(2)
        case "corporation":
            row = replace(row, corporation_id=98000002)
        case "response":
            row = replace(row, response_metadata_id=99)
        case "record_key":
            inputs.blueprints = replace(inputs.blueprints, records={999: row})
    if problem != "record_key":
        inputs.blueprints = replace(inputs.blueprints, records={row.item_id: row})
    with pytest.raises(ValueError):
        collect(inputs)
    inputs.names.assert_not_awaited()


@pytest.mark.parametrize(
    "problem", ["batch", "empty", "missing_corp", "category", "malformed", "conflict"]
)
def test_lookup_failures(
    inputs: Inputs,
    problem: Literal[
        "batch", "empty", "missing_corp", "category", "malformed", "conflict"
    ],
) -> None:
    """Failed requests and invalid names are never disguised as UNKNOWN locations."""
    match problem:
        case "batch":
            failure = Mock(spec=FailedEsiResponse)
            failure.failed_response.error_messages = ["HTTP 503"]
            inputs.names.return_value.append(failure)
        case "empty":
            inputs.names.return_value = []
        case "missing_corp":
            inputs.names.return_value[0].response_data.pop(0)
        case "category":
            inputs.names.return_value[0].response_data[1]["category"] = "inventory_type"
        case "malformed":
            inputs.names.return_value[0].response_data = [{}]
        case "conflict":
            inputs.names.return_value[0].response_data.append(
                {"id": 98000001, "name": "Other Corp", "category": "corporation"}
            )
    with pytest.raises((ValueError, RuntimeError)):
        collect(inputs)


def test_missing_station_name_is_unknown(inputs: Inputs) -> None:
    """An omitted location name retains its raw ID and diagnostic."""
    inputs.names.return_value[0].response_data.pop()
    report = collect(inputs)
    assert report.inventory[0].location_name == "UNKNOWN"
    assert any("60009454" in warning for warning in report.warnings)


def test_location_collision_with_corporation_stays_unknown(inputs: Inputs) -> None:
    """A nonstation location must not reuse a coincidentally resolved corporation name."""
    row = next(iter(inputs.blueprints.records.values()))
    row = replace(row, location_id=inputs.blueprints.corporation_id)
    inputs.blueprints = replace(inputs.blueprints, records={row.item_id: row})
    assert collect(inputs).inventory[0].location_name == "UNKNOWN"


def test_best_original_ties_are_deterministic(inputs: Inputs) -> None:
    """Raw quantity then smallest item ID breaks equal actual ME/TE pairs."""
    base = inputs.blueprints.records[1000000000001]
    rows = [
        replace(base, item_id=30, quantity=2),
        replace(base, item_id=10, quantity=2),
        replace(base, item_id=1, quantity=1),
    ]
    inputs.blueprints = replace(
        inputs.blueprints, records={row.item_id: row for row in rows}
    )
    summary = collect(inputs).owned_bpos[0]
    assert summary.selected_item_id == 10
    assert summary.quantity == 5


@pytest.mark.parametrize(
    "expires,argus,expected",
    [
        (None, None, None),
        ("2026-10-19T00:00:00Z", None, False),
        ("2026-10-18T00:00:00Z", None, True),
        ("2026-10-17T00:00:00Z", "2026-10-19T00:00:00Z", False),
    ],
)
def test_freshness(
    inputs: Inputs, expires: str | None, argus: str | None, expected: bool | None
) -> None:
    """Argus expiry takes precedence and exact expiry is stale."""
    inputs.blueprints = replace(
        inputs.blueprints, expires_at=expires, argus_expires_at=argus
    )
    report = collect(inputs)
    assert report.is_stale is expected
    markdown = render_corporation_blueprints_markdown(report)
    assert ("**STALE:**" in markdown) == (expected is True)
    if expected is None:
        assert "no source expiration" in markdown
    elif expected is False:
        assert "current at report generation" in markdown


def test_all_formats_are_consistent_and_markdown_tables_align(inputs: Inputs) -> None:
    """Four outputs retain counts, IDs, nulls and escaped names without diagnostics."""
    report = collect(inputs)
    before = asdict(report)
    parsed = json.loads(render_corporation_blueprints_json(report))
    owned = list(csv.DictReader(StringIO(render_owned_blueprints_csv(report))))
    missing = list(csv.DictReader(StringIO(render_missing_bpo_csv(report))))
    assert {int(row["item_id"]) for row in owned} == set(inputs.blueprints.records)
    assert {int(row["type_id"]) for row in missing} == {101, 103}
    assert owned[0]["type_name"] == "Blueprint | A\nname"
    assert owned[0]["market_path"] == "Blueprints/Components"
    assert owned[0]["received_at"] == report.received_at
    assert next(row for row in missing if row["type_id"] == "101")["base_price"] == ""
    assert parsed["missing_bpos"][0]["base_price"] is None
    assert parsed["inventory"][2]["runs"] == 7
    markdown = render_corporation_blueprints_markdown(report)
    assert "Blueprint \\| A<br>name" in markdown
    assert "Station \\| A" in markdown
    assert report.received_at in markdown
    assert "**STALE:**" in markdown
    assert all(warning not in markdown for warning in report.warnings)
    for heading in (
        "Owned Blueprint Originals",
        "Missing Blueprint Originals",
        "Originals and Stacks Inventory",
        "Blueprint Copies Inventory",
    ):
        assert f"## {heading}" in markdown
    tables = re.findall(r"(?:^\|.*\n)+", markdown, re.MULTILINE)
    assert tables
    for table in tables:
        counts = [len(re.findall(r"(?<!\\)\|", line)) for line in table.splitlines()]
        assert len(counts) >= 3
        assert len(set(counts)) == 1
    for row in report.inventory:
        assert str(row.item_id) in markdown
    assert asdict(report) == before
    inputs.names.assert_awaited_once()


def test_empty_output_headers_and_missing_inventory_messages(inputs: Inputs) -> None:
    """Empty CSVs retain fixed columns and Markdown shows explicit empty states."""
    inputs.blueprints = replace(inputs.blueprints, records={})
    report = collect(inputs)
    assert "item_id" in render_owned_blueprints_csv(report).splitlines()[0]
    assert list(csv.DictReader(StringIO(render_owned_blueprints_csv(report)))) == []
    assert "No originals or stacks" in render_corporation_blueprints_markdown(report)
    assert "No blueprint copies" in render_corporation_blueprints_markdown(report)


@pytest.mark.parametrize("empty", [False, True])
def test_root_cli_four_files_and_latest_snapshot(
    inputs: Inputs,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    empty: bool,
) -> None:
    """Real readers/collector/renderers select the scoped latest snapshot and write four files."""
    from pfmsoft.eve_argus.cli import app
    from pfmsoft.eve_argus.cli.reports import corporation_blueprints as command
    from pfmsoft.eve_argus.dynamic import util, write
    from pfmsoft.eve_argus.esi.models import GetCorporationsCorporationIdBlueprints
    from pfmsoft.eve_argus.helpers.file_safe_string import file_safe_string
    from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings

    with closing(sqlite3.connect(":memory:")) as connection:
        connection.executescript(util.load_table_definitions())
        source = GetCorporationsCorporationIdBlueprints.model_validate(
            {
                "corporation_id": inputs.blueprints.corporation_id,
                "received_at": "2026-10-16T00:00:00Z",
                "expires_at": None,
                "blueprints": [
                    asdict(row) for row in inputs.blueprints.records.values()
                ],
            }
        )
        write.corporation_blueprints(connection, source)
        write.corporation_blueprints(
            connection,
            source.model_copy(
                update={
                    "received_at": inputs.blueprints.received_at,
                    "blueprints": [] if empty else source.blueprints,
                }
            ),
        )
        write.corporation_blueprints(
            connection,
            source.model_copy(
                update={
                    "received_at": "2026-10-19T00:00:00Z",
                    "corporation_id": 98000002,
                }
            ),
        )
        resources = Mock()
        resources.argus_dynamic_db_connection = connection
        manager = Mock()
        manager.__aenter__ = AsyncMock(return_value=resources)
        manager.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr(command, "EveArgusResources", Mock(return_value=manager))
        type_reader = Mock(return_value=inputs.types)
        monkeypatch.setattr(command.static_read, "types", type_reader)
        monkeypatch.setattr(
            command.static_read, "market_groups", Mock(return_value=inputs.groups)
        )
        settings = Mock(spec=EveArgusSettings)
        settings.corporation_id = None
        settings.character_id = None
        settings.credential_id = None
        args = [
            "reports",
            "corporation-blueprints",
            "--corporation-id",
            "98000001",
            "--to",
            str(tmp_path / "reports"),
        ]
        result = CliRunner().invoke(app, args, obj={SETTINGS_KEY: settings})
        assert result.exit_code == 0, result.output
        stem = f"corporation-blueprints-98000001-{file_safe_string(inputs.blueprints.received_at)}"
        paths = {p.name: p for p in (tmp_path / "reports").iterdir()}
        assert set(paths) == {
            f"{stem}.json",
            f"{stem}.md",
            f"{stem}-owned.csv",
            f"{stem}-missing-bpo.csv",
        }
        parsed = json.loads(paths[f"{stem}.json"].read_text())
        assert parsed["response_metadata_id"] == 2
        assert len(parsed["inventory"]) == (0 if empty else 4)
        assert len(parsed["missing_bpos"]) == (3 if empty else 2)
        assert "UNKNOWN; private" not in result.output
        assert type_reader.call_args.kwargs["only_published"] is False
        inputs.names.assert_awaited_once()

        # Refuse all four existing output names before enrichment.
        denied = CliRunner().invoke(app, args, obj={SETTINGS_KEY: settings})
        assert denied.exit_code != 0
        assert "--overwrite" in denied.output
        inputs.names.assert_awaited_once()
        quiet = CliRunner().invoke(
            app, [*args, "--overwrite", "--quiet"], obj={SETTINGS_KEY: settings}
        )
        assert quiet.exit_code == 0, quiet.output
        assert "Wrote" not in quiet.output


def test_shared_markdown_escaping() -> None:
    """The shared helper preserves jobs behavior and escapes blueprint names safely."""
    from pfmsoft.eve_argus.helpers.markdown import markdown_cell

    assert markdown_cell("<a> | [x]*_\r\nnext") == "&lt;a&gt; \\| \\[x\\]\\*\\_<br>next"


@pytest.mark.parametrize(
    "failure",
    [
        "missing_corporation",
        "no_snapshot",
        "destination_file",
        "collect",
        "render",
        "write",
        "existing_missing_csv",
    ],
)
def test_cli_errors_are_visible_without_partial_success(
    inputs: Inputs,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: Literal[
        "missing_corporation",
        "no_snapshot",
        "destination_file",
        "collect",
        "render",
        "write",
        "existing_missing_csv",
    ],
) -> None:
    """Quiet never hides errors and preflight considers every one of the four files."""
    from jinja2 import UndefinedError

    from pfmsoft.eve_argus.cli import app
    from pfmsoft.eve_argus.cli.reports import corporation_blueprints as command
    from pfmsoft.eve_argus.dynamic.models import CorporationBlueprintsResponse
    from pfmsoft.eve_argus.helpers.file_safe_string import file_safe_string
    from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings

    report = collect(inputs)
    inputs.names.reset_mock()
    settings = Mock(spec=EveArgusSettings)
    settings.corporation_id = 98000001
    resources = Mock()
    manager = Mock()
    manager.__aenter__ = AsyncMock(return_value=resources)
    manager.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(command, "EveArgusResources", Mock(return_value=manager))
    response = CorporationBlueprintsResponse(
        corporation_id=report.corporation_id,
        response_metadata_id=report.response_metadata_id,
        received_at=report.received_at,
        expires_at=report.expires_at,
        argus_expires_at=report.argus_expires_at,
    )
    reader = Mock(return_value=[response])
    monkeypatch.setattr(
        command.dynamic_read, "corporation_blueprints_responses", reader
    )
    monkeypatch.setattr(
        command.dynamic_read,
        "corporation_blueprints",
        Mock(return_value=inputs.blueprints),
    )
    monkeypatch.setattr(command.static_read, "types", Mock(return_value=inputs.types))
    monkeypatch.setattr(
        command.static_read, "market_groups", Mock(return_value=inputs.groups)
    )
    collector = AsyncMock(return_value=report)
    monkeypatch.setattr(command, "collect_corporation_blueprints_report", collector)
    destination = tmp_path / "reports"
    match failure:
        case "missing_corporation":
            settings.corporation_id = None
            expected = "--corporation-id"
        case "no_snapshot":
            reader.return_value = []
            expected = "fetch corporation-blueprints"
        case "destination_file":
            destination.write_text("file")
            expected = "not a directory"
        case "collect":
            collector.side_effect = RuntimeError("Network failed")
            expected = "Network failed"
        case "render":
            monkeypatch.setattr(
                command,
                "render_corporation_blueprints_markdown",
                Mock(side_effect=UndefinedError("Bad template")),
            )
            expected = "Bad template"
        case "write":
            monkeypatch.setattr(
                Path, "open", Mock(side_effect=PermissionError("Denied"))
            )
            expected = "Denied"
        case "existing_missing_csv":
            destination.mkdir()
            stem = f"corporation-blueprints-98000001-{file_safe_string(report.received_at)}"
            (destination / f"{stem}-missing-bpo.csv").write_text("preserve me")
            expected = "--overwrite"
    result = CliRunner().invoke(
        app,
        ["reports", "corporation-blueprints", "--to", str(destination), "--quiet"],
        obj={SETTINGS_KEY: settings},
    )
    assert result.exit_code != 0
    assert expected in " ".join(result.output.split())
    assert "Wrote" not in result.output
    if failure in (
        "missing_corporation",
        "no_snapshot",
        "destination_file",
        "existing_missing_csv",
    ):
        collector.assert_not_awaited()
    if failure == "existing_missing_csv":
        assert len(list(destination.iterdir())) == 1
        assert next(destination.iterdir()).read_text() == "preserve me"


def test_nonmarket_published_originals_remain_visible(inputs: Inputs) -> None:
    """Nonmarket published originals remain visible without expanding comparison."""
    inputs.types[102] = replace(inputs.types[102], published=True)
    report = collect(inputs)
    summary = next(row for row in report.owned_bpos if row.type_id == 102)
    assert summary.in_comparison_universe is False
    assert summary.market_path is None
    assert "Not in market" in render_corporation_blueprints_markdown(report)


def test_no_missing_rows_retains_csv_headers(inputs: Inputs) -> None:
    """A fully owned catalogue has a header-only missing CSV and Markdown message."""
    inputs.types = {100: inputs.types[100], 102: inputs.types[102]}
    records = {
        key: row for key, row in inputs.blueprints.records.items() if row.type_id != 101
    }
    inputs.blueprints = replace(inputs.blueprints, records=records)
    report = collect(inputs)
    assert report.missing_bpos == ()
    assert "type_id" in render_missing_bpo_csv(report).splitlines()[0]
    assert list(csv.DictReader(StringIO(render_missing_bpo_csv(report)))) == []
    assert "No missing blueprint originals" in render_corporation_blueprints_markdown(
        report
    )
