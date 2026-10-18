"""Tests for corporation industry job report name lookups."""

import asyncio
import csv
import json
import re
import sqlite3
from contextlib import closing
from dataclasses import asdict, fields, replace
from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import Literal
from unittest.mock import AsyncMock, Mock

import pytest
from pfmsoft.eve_link import EsiLink, EsiResponse, EsiSchema, FailedEsiResponse
from typer.testing import CliRunner
from whenever import Instant

from pfmsoft.eve_argus.dynamic.models import (
    CorporationIndustryJobRow,
    CorporationIndustryJobsDataset,
)
from pfmsoft.eve_argus.esi import fetch
from pfmsoft.eve_argus.esi.models import GetCorporationsCorporationIdIndustryJobs
from pfmsoft.eve_argus.reports.corp_industry_jobs import (
    CorporationJobsReport,
    collect_corporation_jobs_report,
    collect_universe_name_ids,
)
from pfmsoft.eve_argus.reports.corp_industry_jobs_render import (
    build_markdown_context,
    render_corporation_jobs_csv,
    render_corporation_jobs_json,
    render_corporation_jobs_markdown,
)
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings
from pfmsoft.eve_argus.static.models import (
    IndustryActivityRecord,
    MarketGroupsRecord,
    TypesRecord,
)


@pytest.fixture
def jobs() -> CorporationIndustryJobsDataset:
    """Return a snapshot with public identities and private item locations."""
    job = CorporationIndustryJobRow(
        corporation_id=98000001,
        activity_id=4,
        blueprint_id=1050000000001,
        blueprint_location_id=1040000000001,
        blueprint_type_id=81072,
        completed_character_id=93000002,
        completed_date="2026-10-17T20:00:00Z",
        cost=Decimal("12.34"),
        duration=3600,
        end_date="2026-10-17T20:00:00Z",
        facility_id=60014572,
        installer_id=93000001,
        job_id=669000001,
        licensed_runs=None,
        location_id=60014573,
        output_location_id=1040000000002,
        pause_date=None,
        probability=None,
        product_type_id=81072,
        runs=1,
        start_date="2026-10-17T19:00:00Z",
        status="delivered",
        successful_runs=None,
        response_metadata_id=29,
    )
    return CorporationIndustryJobsDataset(
        corporation_id=job.corporation_id,
        response_metadata_id=job.response_metadata_id,
        received_at="2026-10-17T22:00:00Z",
        expires_at=None,
        argus_expires_at=None,
        records={job.job_id: job},
    )


def test_collects_public_identities_and_locations(
    jobs: CorporationIndustryJobsDataset,
) -> None:
    """Only identities and supported facility/location candidates need ESI names."""
    assert collect_universe_name_ids(jobs) == {
        98000001,
        93000001,
        93000002,
        60014572,
        60014573,
    }


def test_excludes_unrelated_ids_even_when_they_fit_int32(
    jobs: CorporationIndustryJobsDataset,
) -> None:
    """Accepting an integer does not mean ESI resolves the correct kind of ID."""
    job = next(iter(jobs.records.values()))
    job = replace(
        job,
        blueprint_id=34,
        blueprint_location_id=35,
        output_location_id=36,
        job_id=37,
    )
    result = collect_universe_name_ids(replace(jobs, records={job.job_id: job}))

    assert result.isdisjoint({4, 29, 34, 35, 36, 37, 81072})


def test_deduplicates_ids_and_ignores_absent_completing_character(
    jobs: CorporationIndustryJobsDataset,
) -> None:
    """Repeated characters/stations require one lookup and None requires none."""
    job = next(iter(jobs.records.values()))
    job = replace(job, completed_character_id=None, location_id=job.facility_id)
    second = replace(job, job_id=job.job_id + 1)
    snapshot = replace(jobs, records={job.job_id: job, second.job_id: second})

    assert collect_universe_name_ids(snapshot) == {98000001, 93000001, 60014572}


@pytest.mark.parametrize("location_id", [0, -1, 2**31, 1040000000001])
def test_excludes_unsupported_facility_and_location_values(
    jobs: CorporationIndustryJobsDataset, location_id: int
) -> None:
    """Private structures and invalid locations must not poison a names batch."""
    job = next(iter(jobs.records.values()))
    job = replace(job, facility_id=location_id, location_id=location_id)

    assert collect_universe_name_ids(replace(jobs, records={job.job_id: job})) == {
        98000001,
        93000001,
        93000002,
    }


@pytest.mark.parametrize("location_id", [1, 2**31 - 1])
def test_preserves_int32_boundary_candidates(
    jobs: CorporationIndustryJobsDataset, location_id: int
) -> None:
    """The range guard admits both positive int32 boundaries for later validation."""
    job = next(iter(jobs.records.values()))
    job = replace(job, facility_id=location_id, location_id=location_id)

    assert collect_universe_name_ids(replace(jobs, records={job.job_id: job})) == {
        98000001,
        93000001,
        93000002,
        location_id,
    }


def test_empty_snapshot_still_resolves_the_corporation(
    jobs: CorporationIndustryJobsDataset,
) -> None:
    """A zero-job report still needs its corporation's name."""
    assert collect_universe_name_ids(replace(jobs, records={})) == {98000001}


@pytest.fixture
def type_record() -> TypesRecord:
    """Return an unpublished type with a blueprint market group."""
    return TypesRecord(
        type_id=81072,
        name="Blueprint | test\nname",
        market_group_id=10,
        base_price=None,
        capacity=None,
        description=None,
        faction_id=None,
        graphic_id=None,
        group_id=1,
        icon_id=None,
        is_dynamic_type=None,
        is_repackable=None,
        mass=None,
        meta_group_id=None,
        meta_level=None,
        packaged_volume=None,
        portion_size=1,
        published=False,
        race_id=None,
        radius=None,
        ship_tree_group_id=None,
        sound_id=None,
        tech_level=None,
        variation_parent_type_id=None,
        volume=None,
    )


@pytest.fixture
def names_fetch(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Mock successful singleton/batched ESI name responses without network access."""
    response = Mock(spec=EsiResponse)
    response.response_data = [
        {"id": 98000001, "name": "Test Corp", "category": "corporation"},
        {"id": 93000001, "name": "Installer", "category": "character"},
        {"id": 93000002, "name": "Completer", "category": "character"},
        {"id": 60014572, "name": "Factory", "category": "station"},
        {"id": 60014573, "name": "Station", "category": "station"},
    ]
    response.response.metadata.received_at = "2026-10-18T00:00:00Z"
    response.response.metadata.expires_at_instant = None
    mocked = AsyncMock(return_value=[response])
    monkeypatch.setattr(fetch, "universe_names", mocked)
    return mocked


def collect(
    jobs: CorporationIndustryJobsDataset, type_record: TypesRecord
) -> CorporationJobsReport:
    """Collect with deterministic static data and report time."""
    return asyncio.run(
        collect_corporation_jobs_report(
            jobs=jobs,
            types={type_record.type_id: type_record},
            market_groups={
                10: MarketGroupsRecord(
                    market_group_id=10,
                    description="",
                    has_types=True,
                    icon_id=None,
                    int_path=(1, 10),
                    str_path=("Blueprints", "Components"),
                    name="Components",
                    parent_group_id=1,
                    types=(type_record.type_id,),
                )
            },
            industry_activities={
                4: IndustryActivityRecord(
                    activity_id=4,
                    description="",
                    name="Material efficiency research",
                )
            },
            esi_link=Mock(spec=EsiLink),
            schema=Mock(spec=EsiSchema),
            generated_at=Instant.parse_iso("2026-10-18T00:00:00Z"),
        )
    )


def test_collect_preserves_source_and_enriches_once(
    jobs: CorporationIndustryJobsDataset,
    type_record: TypesRecord,
    names_fetch: AsyncMock,
) -> None:
    """All source fields survive alongside static names and unresolved locations."""
    report = collect(jobs, type_record)
    row = report.jobs[0]
    for field in fields(CorporationIndustryJobRow):
        assert getattr(row, field.name) == getattr(
            next(iter(jobs.records.values())), field.name
        )
    assert row.blueprint_name == type_record.name
    assert row.product_name == type_record.name
    assert row.activity_name == "Material efficiency research"
    assert row.blueprint_market_path == ("Blueprints", "Components")
    assert row.blueprint_market_group_id == 10
    assert row.blueprint_location_name == row.output_location_name == "UNKNOWN"
    assert row.facility_name == "Factory"
    assert row.location_name == "Station"
    assert row.completed_character_name == "Completer"
    assert report.received_at == jobs.received_at
    assert report.corporation_name == "Test Corp"
    assert report.generated_at == "2026-10-18T00:00:00Z"
    names_fetch.assert_awaited_once()
    assert names_fetch.call_args.kwargs["ids"] == collect_universe_name_ids(jobs)


@pytest.mark.parametrize(
    "status,expected",
    [
        ("active", "ready"),
        ("paused", "paused"),
        ("delivered", "delivered"),
        ("cancelled", "cancelled"),
        ("reverted", "reverted"),
        ("mystery", "mystery"),
    ],
)
def test_status_boundary_preserves_raw_status(
    jobs: CorporationIndustryJobsDataset,
    type_record: TypesRecord,
    names_fetch: AsyncMock,
    status: str,
    expected: str,
) -> None:
    """Only active jobs become ready at the exact end-time boundary."""
    job = replace(
        next(iter(jobs.records.values())),
        status=status,
        end_date="2026-10-18T00:00:00Z",
    )
    row = collect(replace(jobs, records={job.job_id: job}), type_record).jobs[0]
    assert row.status == status
    assert row.effective_status == expected
    assert row.remaining_seconds is None


def test_active_remaining_and_null_fields(
    jobs: CorporationIndustryJobsDataset,
    type_record: TypesRecord,
    names_fetch: AsyncMock,
) -> None:
    """Active countdowns and absent optional names are represented explicitly."""
    job = replace(
        next(iter(jobs.records.values())),
        status="active",
        end_date="2026-10-18T01:01:01Z",
        product_type_id=None,
        completed_character_id=None,
        completed_date=None,
    )
    row = collect(
        replace(jobs, records={job.job_id: job}),
        replace(type_record, market_group_id=None),
    ).jobs[0]
    assert row.remaining_seconds == 3661
    assert row.product_name is None
    assert row.completed_character_name is None
    assert row.blueprint_market_path is None


@pytest.mark.parametrize(
    "problem", ["failed", "empty", "missing", "category", "malformed"]
)
def test_lookup_errors_are_explicit(
    jobs: CorporationIndustryJobsDataset,
    type_record: TypesRecord,
    names_fetch: AsyncMock,
    problem: Literal["failed", "empty", "missing", "category", "malformed"],
) -> None:
    """API, missing-identity, category, and validation failures never look successful."""
    match problem:
        case "failed":
            failed = Mock(spec=FailedEsiResponse)
            failed.failed_response.error_messages = ["HTTP 503"]
            names_fetch.return_value = [failed]
        case "empty":
            names_fetch.return_value = []
        case "missing":
            names_fetch.return_value[0].response_data = []
        case "category":
            names_fetch.return_value[0].response_data[0]["category"] = "inventory_type"
        case "malformed":
            names_fetch.return_value[0].response_data = [{"id": "bad"}]
    with pytest.raises((ValueError, RuntimeError)):
        collect(jobs, type_record)


def test_missing_public_location_is_unknown_with_warning(
    jobs: CorporationIndustryJobsDataset,
    type_record: TypesRecord,
    names_fetch: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An omitted station name is a visible enrichment limitation."""
    names_fetch.return_value[0].response_data.pop()
    report = collect(jobs, type_record)
    assert report.jobs[0].location_name == "UNKNOWN"
    assert any("60014573" in warning for warning in report.warnings)
    assert "60014573" in caplog.text


@pytest.mark.parametrize("problem", ["type", "activity", "market_group"])
def test_missing_static_data_is_explicit(
    jobs: CorporationIndustryJobsDataset,
    type_record: TypesRecord,
    names_fetch: AsyncMock,
    problem: Literal["type", "activity", "market_group"],
) -> None:
    """Missing static references are not silently replaced by invented names."""
    job = next(iter(jobs.records.values()))
    match problem:
        case "type":
            job = replace(job, product_type_id=999)
        case "activity":
            job = replace(job, activity_id=999)
        case "market_group":
            type_record = replace(type_record, market_group_id=999)
    with pytest.raises(ValueError, match="999"):
        collect(replace(jobs, records={job.job_id: job}), type_record)


def test_renderers_preserve_records_precision_and_metadata(
    jobs: CorporationIndustryJobsDataset,
    type_record: TypesRecord,
    names_fetch: AsyncMock,
) -> None:
    """Formats share the source records; CSV quotes cells and JSON preserves nulls."""
    report = collect(replace(jobs, expires_at="2026-10-17T23:00:00Z"), type_record)
    parsed = json.loads(render_corporation_jobs_json(report))
    assert parsed["jobs"][0]["cost"] == "12.34"
    assert parsed["jobs"][0]["licensed_runs"] is None
    assert parsed["jobs"][0]["blueprint_market_path"] == ["Blueprints", "Components"]
    rows = list(csv.DictReader(StringIO(render_corporation_jobs_csv(report))))
    assert rows[0]["blueprint_name"] == type_record.name
    assert rows[0]["cost"] == "12.34"
    assert rows[0]["expires_at"] == report.expires_at
    assert rows[0]["blueprint_market_path"] == "Blueprints/Components"
    assert rows[0]["licensed_runs"] == ""
    markdown = render_corporation_jobs_markdown(report)
    assert "Blueprint \\| test<br>name" in markdown
    assert report.received_at in markdown
    assert report.expires_at is not None
    assert report.expires_at in markdown
    assert "STALE" in markdown
    assert "UNKNOWN" in markdown
    assert "Name Resolution Limitations" not in markdown
    assert all(warning not in markdown for warning in report.warnings)
    assert str(report.jobs[0].job_id) in markdown
    assert "12.34" not in markdown  # Monetary detail remains in JSON/CSV.
    names_fetch.assert_awaited_once()


def test_empty_snapshot_renders_all_formats(
    jobs: CorporationIndustryJobsDataset,
    type_record: TypesRecord,
    names_fetch: AsyncMock,
) -> None:
    """Empty reports remain meaningful and CSV retains fixed headers."""
    report = collect(replace(jobs, records={}), type_record)
    assert json.loads(render_corporation_jobs_json(report))["jobs"] == []
    csv_text = render_corporation_jobs_csv(report)
    assert "job_id" in csv_text.splitlines()[0]
    assert list(csv.DictReader(StringIO(csv_text))) == []
    assert "No industry jobs" in render_corporation_jobs_markdown(report)


def test_summary_counts_status_sorting_and_duplicate_names(
    jobs: CorporationIndustryJobsDataset,
    type_record: TypesRecord,
    names_fetch: AsyncMock,
) -> None:
    """Summaries use installer IDs; completed jobs do not inflate current totals."""
    base = next(iter(jobs.records.values()))
    source = [
        replace(
            base,
            job_id=base.job_id + index,
            status=status,
            end_date="2026-10-18T00:00:00Z",
        )
        for index, status in enumerate(
            (
                "active",
                "paused",
                "delivered",
                "ready",
                "cancelled",
                "reverted",
                "mystery",
            )
        )
    ]
    source.append(replace(base, installer_id=93000002, job_id=base.job_id + 10))
    names_fetch.return_value[0].response_data[2]["name"] = "Installer"
    report = collect(
        replace(jobs, records={job.job_id: job for job in reversed(source)}),
        type_record,
    )
    assert [job.job_id for job in report.jobs] == sorted(job.job_id for job in source)
    context = build_markdown_context(report)
    first, second = context.summaries
    assert first.installer_id != second.installer_id
    assert asdict(first.me) == {"total": 3, "active": 0, "ready": 2, "paused": 1}
    assert first.research == first.me
    assert second.research.total == 0
    ready = next(table for table in context.tables if table.status == "ready")
    assert [job.job_id for job in ready.jobs] == [base.job_id, base.job_id + 3]
    other = next(table for table in context.tables if table.status == "other")
    assert other.jobs[0].status == "mystery"
    markdown = render_corporation_jobs_markdown(report)
    for heading in (
        "Character Summary",
        "Ready Jobs",
        "Active Jobs",
        "Paused Jobs",
        "Delivered Jobs",
        "Cancelled Jobs",
        "Reverted Jobs",
        "Other Jobs",
    ):
        assert f"## {heading}" in markdown


def test_markdown_tables_have_separate_aligned_lines(
    jobs: CorporationIndustryJobsDataset,
    type_record: TypesRecord,
    names_fetch: AsyncMock,
) -> None:
    """Headers, separators, and data rows must form actual Markdown tables."""
    report = collect(jobs, type_record)
    markdown = render_corporation_jobs_markdown(report)
    table_lines = [line for line in markdown.splitlines() if line.startswith("|")]
    assert len(table_lines) == 6  # Two three-line tables: summary and delivered.
    header = [cell.strip() for cell in re.split(r"(?<!\\)\|", table_lines[3])[1:-1]]
    values = [cell.strip() for cell in re.split(r"(?<!\\)\|", table_lines[5])[1:-1]]
    facility_index = header.index("Facility")
    assert header[facility_index + 1] == "Location"
    assert values[facility_index : facility_index + 2] == [
        "Factory (60014572)",
        "Station (60014573)",
    ]
    for index in (0, 3):
        widths = [
            len(re.findall(r"(?<!\\)\|", line))
            for line in table_lines[index : index + 3]
        ]
        assert widths[0] == widths[1] == widths[2]
    assert (
        "\n\n|"
        not in markdown[markdown.index("| Character") : markdown.index("## Ready")]
    )


@pytest.mark.parametrize(
    "end_date,expected",
    [
        ("2026-10-19T02:03:04Z", "1d 2h 3m 4s"),
        ("2026-10-18T00:00:01Z", "1s"),
        ("2026-10-18T00:00:00.001Z", "1s"),
    ],
)
def test_active_markdown_countdown(
    jobs: CorporationIndustryJobsDataset,
    type_record: TypesRecord,
    names_fetch: AsyncMock,
    end_date: str,
    expected: str,
) -> None:
    """Active countdowns include whole units and round positive fractions upward."""
    job = replace(next(iter(jobs.records.values())), end_date=end_date, status="active")
    report = collect(replace(jobs, records={job.job_id: job}), type_record)
    assert expected in render_corporation_jobs_markdown(report)


@pytest.mark.parametrize(
    "expires,argus,expected",
    [
        (None, None, None),
        ("2026-10-19T00:00:00Z", None, False),
        ("2026-10-18T00:00:00Z", None, True),
        ("2026-10-17T00:00:00Z", "2026-10-19T00:00:00Z", False),
        ("2026-10-19T00:00:00Z", "2026-10-17T00:00:00Z", True),
    ],
)
def test_freshness_uses_argus_expiry_first(
    jobs: CorporationIndustryJobsDataset,
    type_record: TypesRecord,
    names_fetch: AsyncMock,
    expires: str | None,
    argus: str | None,
    expected: bool | None,
) -> None:
    """Freshness is unknown without expiry and stale at the exact expiry boundary."""
    report = collect(
        replace(jobs, expires_at=expires, argus_expires_at=argus), type_record
    )
    assert report.is_stale is expected
    markdown = render_corporation_jobs_markdown(report)
    assert ("**STALE:**" in markdown) == (expected is True)
    if expected is None:
        assert "no source expiration" in markdown


@pytest.mark.parametrize(
    "activity,category,research",
    [
        (1, "manufacturing", False),
        (3, "te", True),
        (4, "me", True),
        (5, "copying", True),
        (8, "invention", True),
        (11, "reactions", False),
    ],
)
def test_summary_activity_categories(
    jobs: CorporationIndustryJobsDataset,
    type_record: TypesRecord,
    names_fetch: AsyncMock,
    activity: int,
    category: str,
    research: bool,
) -> None:
    """Every established activity contributes to its category and research aggregate."""
    report = collect(jobs, type_record)
    row = replace(report.jobs[0], activity_id=activity, effective_status="active")
    summary = build_markdown_context(replace(report, jobs=(row,))).summaries[0]
    assert getattr(summary, category).active == 1
    assert summary.research.total == int(research)


def test_decimal_precision_and_render_purity(
    jobs: CorporationIndustryJobsDataset,
    type_record: TypesRecord,
    names_fetch: AsyncMock,
) -> None:
    """Rendering large precise costs is lossless and does not mutate collected data."""
    report = collect(jobs, type_record)
    cost = Decimal("12345678901234567890.12")
    report = replace(report, jobs=(replace(report.jobs[0], cost=cost),))
    before = asdict(report)
    assert json.loads(render_corporation_jobs_json(report))["jobs"][0]["cost"] == str(
        cost
    )
    assert list(csv.DictReader(StringIO(render_corporation_jobs_csv(report))))[0][
        "cost"
    ] == str(cost)
    render_corporation_jobs_markdown(report)
    assert asdict(report) == before


@pytest.mark.parametrize("field", ["corporation_id", "response_metadata_id"])
def test_rejects_rows_from_other_snapshots(
    jobs: CorporationIndustryJobsDataset,
    type_record: TypesRecord,
    names_fetch: AsyncMock,
    field: str,
) -> None:
    """Mixing snapshots must not create a success-shaped report."""
    row = next(iter(jobs.records.values()))
    row = replace(row, **{field: getattr(row, field) + 1})
    with pytest.raises(ValueError, match="snapshot"):
        collect(replace(jobs, records={row.job_id: row}), type_record)


@pytest.mark.parametrize("field", ["facility_id", "location_id"])
def test_private_structure_location_names_are_unknown(
    jobs: CorporationIndustryJobsDataset,
    type_record: TypesRecord,
    names_fetch: AsyncMock,
    field: str,
) -> None:
    """64-bit facility/installation locations do not enter the ESI request."""
    row = replace(next(iter(jobs.records.values())), **{field: 1040000000003})
    report = collect(replace(jobs, records={row.job_id: row}), type_record)
    assert getattr(report.jobs[0], field.removesuffix("_id") + "_name") == "UNKNOWN"
    assert 1040000000003 not in names_fetch.call_args.kwargs["ids"]


def test_wrong_location_category_is_not_treated_as_a_name(
    jobs: CorporationIndustryJobsDataset,
    type_record: TypesRecord,
    names_fetch: AsyncMock,
) -> None:
    """A successful lookup for an unrelated namespace is an explicit error."""
    names_fetch.return_value[0].response_data[-1]["category"] = "inventory_type"
    with pytest.raises(ValueError, match="Expected station"):
        collect(jobs, type_record)


@pytest.mark.parametrize("empty", [False, True])
def test_cli_end_to_end_with_real_collection_and_renderers(
    jobs: CorporationIndustryJobsDataset,
    type_record: TypesRecord,
    names_fetch: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    empty: bool,
) -> None:
    """Read real snapshots, enrich once, and write matching outputs via the root CLI."""
    from pfmsoft.eve_argus.cli import app
    from pfmsoft.eve_argus.cli.reports import corporation_jobs as command
    from pfmsoft.eve_argus.dynamic import util, write

    with closing(sqlite3.connect(":memory:")) as connection:
        connection.executescript(util.load_table_definitions())
        source = GetCorporationsCorporationIdIndustryJobs.model_validate(
            {
                "corporation_id": jobs.corporation_id,
                "received_at": "2026-10-16T00:00:00Z",
                "expires_at": None,
                "industry_jobs": [asdict(job) for job in jobs.records.values()],
            }
        )
        write.corporation_industry_jobs(connection, source)
        latest = source.model_copy(
            update={
                "received_at": jobs.received_at,
                "industry_jobs": [] if empty else source.industry_jobs,
            }
        )
        write.corporation_industry_jobs(connection, latest)
        resources = Mock()
        resources.argus_dynamic_db_connection = connection
        manager = Mock()
        manager.__aenter__ = AsyncMock(return_value=resources)
        manager.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr(command, "EveArgusResources", Mock(return_value=manager))
        monkeypatch.setattr(
            command.static_read,
            "types",
            Mock(
                return_value={
                    type_record.type_id: replace(type_record, market_group_id=None),
                }
            ),
        )
        monkeypatch.setattr(command.static_read, "market_groups", Mock(return_value={}))
        monkeypatch.setattr(
            command.static_read,
            "industry_activities",
            Mock(
                return_value={
                    4: IndustryActivityRecord(
                        activity_id=4, description="", name="ME research"
                    ),
                }
            ),
        )
        settings = Mock(spec=EveArgusSettings)
        settings.corporation_id = jobs.corporation_id
        result = CliRunner().invoke(
            app,
            ["reports", "corporation-jobs", "--to", str(tmp_path)],
            obj={SETTINGS_KEY: settings},
        )
    assert result.exit_code == 0, result.output
    parsed = json.loads(next(tmp_path.glob("*.json")).read_text())
    csv_rows = list(csv.DictReader(StringIO(next(tmp_path.glob("*.csv")).read_text())))
    markdown = next(tmp_path.glob("*.md")).read_text()
    assert parsed["response_metadata_id"] == 2
    assert parsed["received_at"] == jobs.received_at
    assert len(parsed["jobs"]) == len(csv_rows) == (0 if empty else 1)
    if empty:
        assert "No industry jobs" in markdown
    else:
        assert parsed["jobs"][0]["cost"] == csv_rows[0]["cost"] == "12.34"
        assert str(parsed["jobs"][0]["job_id"]) in markdown
    names_fetch.assert_awaited_once()
