"""Tests for stored corporation-job report CLI orchestration."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from unittest.mock import AsyncMock, Mock

import pytest
from jinja2 import UndefinedError
from typer.testing import CliRunner, Result

from pfmsoft.eve_argus.cli import app
from pfmsoft.eve_argus.cli.reports import corporation_jobs as command
from pfmsoft.eve_argus.dynamic import util, write
from pfmsoft.eve_argus.dynamic.models import CorporationIndustryJobsDataset
from pfmsoft.eve_argus.esi.models import GetCorporationsCorporationIdIndustryJobs
from pfmsoft.eve_argus.helpers.file_safe_string import file_safe_string
from pfmsoft.eve_argus.reports.corp_industry_jobs import CorporationJobsReport
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings


@dataclass(slots=True, kw_only=True)
class CommandEnvironment:
    """Mocked external resources with a real in-memory dynamic database."""

    connection: sqlite3.Connection
    settings: EveArgusSettings
    collector: AsyncMock
    type_reader: Mock


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[CommandEnvironment]:
    """Isolate databases/settings and substitute enrichment without live ESI calls."""
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.executescript(util.load_table_definitions())
        settings = Mock(spec=EveArgusSettings)
        settings.corporation_id = 98000001
        settings.character_id = None
        settings.credential_id = None
        resources = Mock()
        resources.argus_dynamic_db_connection = connection
        resources.argus_static_db_connection = Mock()
        manager = Mock()
        manager.__aenter__ = AsyncMock(return_value=resources)
        manager.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr(command, "EveArgusResources", Mock(return_value=manager))
        for name in ("types", "market_groups", "industry_activities"):
            monkeypatch.setattr(command.static_read, name, Mock(return_value={}))
        type_reader = command.static_read.types
        assert isinstance(type_reader, Mock)

        async def collect_report(**kwargs: object) -> CorporationJobsReport:
            jobs = kwargs["jobs"]
            assert isinstance(jobs, CorporationIndustryJobsDataset)
            return CorporationJobsReport(
                corporation_id=jobs.corporation_id,
                corporation_name="Test Corp",
                response_metadata_id=jobs.response_metadata_id,
                received_at=jobs.received_at,
                expires_at=jobs.expires_at,
                argus_expires_at=jobs.argus_expires_at,
                generated_at="2026-10-18T00:00:00Z",
                is_stale=True,
                jobs=(),
                warnings=("Location 1040000000001: UNKNOWN; private location.",),
            )

        collector = AsyncMock(side_effect=collect_report)
        monkeypatch.setattr(command, "collect_corporation_jobs_report", collector)
        yield CommandEnvironment(
            connection=connection,
            settings=settings,
            collector=collector,
            type_reader=type_reader,
        )


def save_snapshot(
    environment: CommandEnvironment,
    *,
    received_at: str = "2026-10-17T22:07:37.553890662Z",
    corporation_id: int = 98000001,
) -> None:
    """Persist an empty snapshot using the production writer."""
    write.corporation_industry_jobs(
        environment.connection,
        GetCorporationsCorporationIdIndustryJobs(
            corporation_id=corporation_id,
            received_at=received_at,
            expires_at="2026-10-17T23:00:00Z",
            industry_jobs=[],
        ),
    )


def invoke(environment: CommandEnvironment, *args: str) -> Result:
    """Run the registered CLI with isolated settings."""
    return CliRunner().invoke(
        app,
        ["reports", "corporation-jobs", *args],
        obj={SETTINGS_KEY: environment.settings},
    )


def test_latest_snapshot_writes_three_timestamped_files(
    environment: CommandEnvironment,
    tmp_path: Path,
) -> None:
    """Select by receipt time and corporation, not insertion order or record count."""
    timestamp = "2026-10-17T22:07:37.553890662Z"
    save_snapshot(environment)
    save_snapshot(environment, received_at="2026-10-16T00:00:00Z")
    save_snapshot(
        environment, received_at="2026-10-18T00:00:00Z", corporation_id=98000002
    )
    destination = tmp_path / "new-directory"
    result = invoke(environment, "--to", str(destination))
    assert result.exit_code == 0, result.output
    stem = f"corporation-jobs-98000001-{file_safe_string(timestamp)}"
    assert {path.name for path in destination.iterdir()} == {
        f"{stem}.json",
        f"{stem}.csv",
        f"{stem}.md",
    }
    parsed = json.loads((destination / f"{stem}.json").read_text())
    assert parsed["received_at"] == timestamp
    assert parsed["jobs"] == []
    environment.collector.assert_awaited_once()
    assert environment.collector.call_args.kwargs["jobs"].response_metadata_id == 1
    assert environment.type_reader.call_args.kwargs["only_published"] is False


def test_explicit_corporation_overrides_default(
    environment: CommandEnvironment,
    tmp_path: Path,
) -> None:
    """Only a corporation ID is needed; no character or credential is required."""
    save_snapshot(environment, corporation_id=98000002)
    result = invoke(environment, "--to", str(tmp_path), "--corporation-id", "98000002")
    assert result.exit_code == 0, result.output
    assert environment.collector.call_args.kwargs["jobs"].corporation_id == 98000002


def test_existing_files_require_overwrite(
    environment: CommandEnvironment,
    tmp_path: Path,
) -> None:
    """Reruns do not change previous output without explicit overwrite permission."""
    save_snapshot(environment)
    first = invoke(environment, "--to", str(tmp_path))
    assert first.exit_code == 0
    path = next(tmp_path.glob("*.json"))
    path.write_text("keep me")
    environment.collector.reset_mock()
    second = invoke(environment, "--to", str(tmp_path))
    assert second.exit_code != 0
    assert "--overwrite" in second.output
    assert path.read_text() == "keep me"
    environment.collector.assert_not_awaited()
    third = invoke(environment, "--to", str(tmp_path), "--overwrite")
    assert third.exit_code == 0, third.output
    assert json.loads(path.read_text())["jobs"] == []


@pytest.mark.parametrize(
    "failure", ["missing_corporation", "no_snapshot", "destination_file"]
)
def test_input_errors_are_actionable(
    environment: CommandEnvironment,
    tmp_path: Path,
    failure: Literal["missing_corporation", "no_snapshot", "destination_file"],
) -> None:
    """Bad input produces a nonzero exit and an explanatory error."""
    destination = tmp_path / "reports"
    match failure:
        case "missing_corporation":
            environment.settings.corporation_id = None
            expected = "--corporation-id"
        case "no_snapshot":
            expected = "fetch corporation-jobs"
        case "destination_file":
            save_snapshot(environment)
            destination.write_text("not a directory")
            expected = "directory"
    result = invoke(environment, "--to", str(destination), "--quiet")
    assert result.exit_code != 0
    assert expected in " ".join(result.output.split())
    environment.collector.assert_not_awaited()


@pytest.mark.parametrize("failure", ["collect", "render", "write"])
def test_pipeline_failures_are_visible(
    environment: CommandEnvironment,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Literal["collect", "render", "write"],
) -> None:
    """Enrichment/rendering failure writes nothing; write failure reports no success."""
    save_snapshot(environment)
    destination = tmp_path / "reports"
    match failure:
        case "collect":
            environment.collector.side_effect = RuntimeError("ESI unavailable")
            expected = "ESI unavailable"
        case "render":
            monkeypatch.setattr(
                command,
                "render_corporation_jobs_markdown",
                Mock(side_effect=UndefinedError("Invalid template data")),
            )
            expected = "Invalid template data"
        case "write":
            monkeypatch.setattr(
                Path, "open", Mock(side_effect=PermissionError("Denied"))
            )
            expected = "Denied"
    result = invoke(environment, "--to", str(destination), "--quiet")
    assert result.exit_code != 0
    assert expected in result.output
    assert "Wrote" not in result.output
    assert not destination.exists() or not list(destination.iterdir())


def test_quiet_hides_progress_not_warnings(
    environment: CommandEnvironment,
    tmp_path: Path,
) -> None:
    """Stale data warnings remain visible in quiet mode."""
    save_snapshot(environment)
    result = invoke(environment, "--to", str(tmp_path), "--quiet")
    assert result.exit_code == 0, result.output
    assert "Wrote" not in result.output
    assert "expired" in result.output
    assert "1040000000001" not in result.output


def test_name_resolution_warnings_are_not_printed(
    environment: CommandEnvironment,
    tmp_path: Path,
) -> None:
    """Normal CLI output omits name-resolution diagnostics retained in JSON."""
    save_snapshot(environment)
    result = invoke(environment, "--to", str(tmp_path))
    assert result.exit_code == 0, result.output
    assert "Wrote" in result.output
    assert "Location 1040000000001" not in result.output
    parsed = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert parsed["warnings"]
    markdown = next(tmp_path.glob("*.md")).read_text()
    assert "Name Resolution Limitations" not in markdown
    assert "Location 1040000000001" not in markdown
