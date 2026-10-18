"""Pure JSON, CSV, and Jinja Markdown renderers for collected corporation jobs."""

import csv
from collections import defaultdict
from dataclasses import asdict, dataclass, fields
from io import StringIO

from jinja2 import Environment, PackageLoader, StrictUndefined
from mdformat import text as mdformat_text  # type: ignore
from pydantic import TypeAdapter
from whenever import Instant

from pfmsoft.eve_argus.helpers.markdown import markdown_cell as _markdown_cell
from pfmsoft.eve_argus.reports.corp_industry_jobs import (
    CorporationJobReportRow,
    CorporationJobsReport,
)

_REPORT_ADAPTER = TypeAdapter(CorporationJobsReport)
_ACTIVITY_CATEGORIES = {
    1: "manufacturing",
    3: "te",
    4: "me",
    5: "copying",
    8: "invention",
    11: "reactions",
}
_STATUSES = ("ready", "active", "paused", "delivered", "cancelled", "reverted")


@dataclass(slots=True, kw_only=True, frozen=True)
class JobCounts:
    """Current total, active, ready, and paused counts, excluding historical jobs."""

    total: int = 0
    active: int = 0
    ready: int = 0
    paused: int = 0


@dataclass(slots=True, kw_only=True, frozen=True)
class CharacterSummary:
    """Per-installer counts; research aggregates copying, invention, ME, and TE."""

    installer_id: int
    installer_name: str
    manufacturing: JobCounts
    research: JobCounts
    copying: JobCounts
    invention: JobCounts
    me: JobCounts
    te: JobCounts
    reactions: JobCounts


@dataclass(slots=True, kw_only=True, frozen=True)
class StatusTable:
    """A sorted status section for the Markdown template."""

    status: str
    title: str
    jobs: tuple[CorporationJobReportRow, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class CorporationJobsContext:
    """Typed Markdown template context, with no further collection or clock reads."""

    report: CorporationJobsReport
    summaries: tuple[CharacterSummary, ...]
    tables: tuple[StatusTable, ...]


def _counts(rows: list[CorporationJobReportRow]) -> JobCounts:
    active = sum(row.effective_status == "active" for row in rows)
    ready = sum(row.effective_status == "ready" for row in rows)
    paused = sum(row.effective_status == "paused" for row in rows)
    return JobCounts(
        total=active + ready + paused, active=active, ready=ready, paused=paused
    )


def build_markdown_context(report: CorporationJobsReport) -> CorporationJobsContext:
    """Group by installer identity and effective status without mutating report data."""
    grouped: dict[int, list[CorporationJobReportRow]] = defaultdict(list)
    for row in report.jobs:
        grouped[row.installer_id].append(row)
    summaries: list[CharacterSummary] = []
    for installer_id, rows in grouped.items():
        by_category: dict[str, list[CorporationJobReportRow]] = defaultdict(list)
        for row in rows:
            category = _ACTIVITY_CATEGORIES.get(row.activity_id)
            if category is not None:
                by_category[category].append(row)
        summaries.append(
            CharacterSummary(
                installer_id=installer_id,
                installer_name=rows[0].installer_name,
                manufacturing=_counts(by_category["manufacturing"]),
                research=_counts([
                    row
                    for category in ("copying", "invention", "me", "te")
                    for row in by_category[category]
                ]),
                copying=_counts(by_category["copying"]),
                invention=_counts(by_category["invention"]),
                me=_counts(by_category["me"]),
                te=_counts(by_category["te"]),
                reactions=_counts(by_category["reactions"]),
            )
        )
    tables: list[StatusTable] = []
    for status in (*_STATUSES, "other"):
        rows = [
            row
            for row in report.jobs
            if (row.effective_status if row.effective_status in _STATUSES else "other")
            == status
        ]
        rows.sort(key=lambda row: (Instant.parse_iso(row.end_date), row.job_id))
        tables.append(
            StatusTable(status=status, title=f"{status.title()} Jobs", jobs=tuple(rows))
        )
    return CorporationJobsContext(
        report=report,
        summaries=tuple(
            sorted(summaries, key=lambda row: (row.installer_name, row.installer_id))
        ),
        tables=tuple(tables),
    )


def render_corporation_jobs_json(report: CorporationJobsReport) -> str:
    """Serialize metadata and jobs, preserving nulls and Decimal costs as strings."""
    return _REPORT_ADAPTER.dump_json(report, indent=2).decode("utf-8") + "\n"


def render_corporation_jobs_csv(report: CorporationJobsReport) -> str:
    """Render fixed columns with repeated metadata and slash-separated market paths.

    Optional None values are empty cells. Decimal values are written as strings,
    never floats. An empty snapshot produces headers only.
    """
    metadata: dict[str, str | bool | None] = {
        "corporation_name": report.corporation_name,
        "received_at": report.received_at,
        "expires_at": report.expires_at,
        "argus_expires_at": report.argus_expires_at,
        "generated_at": report.generated_at,
        "is_stale": report.is_stale,
    }
    stream = StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=[
            *metadata,
            *(field.name for field in fields(CorporationJobReportRow)),
        ],
        lineterminator="\n",
    )
    writer.writeheader()
    for job in report.jobs:
        row = asdict(job)
        row["blueprint_market_path"] = (
            "/".join(job.blueprint_market_path)
            if job.blueprint_market_path is not None
            else None
        )
        writer.writerow(metadata | row)
    return stream.getvalue()


def _remaining(seconds: int) -> str:
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    return (
        " ".join(
            f"{value}{unit}"
            for value, unit in (
                (days, "d"),
                (hours, "h"),
                (minutes, "m"),
                (seconds, "s"),
            )
            if value
        )
        or "0s"
    )


def render_corporation_jobs_markdown(report: CorporationJobsReport) -> str:
    """Render character summaries and status tables from packaged Jinja templates."""
    environment = Environment(
        loader=PackageLoader("pfmsoft.eve_argus.templates", "corp_industry_jobs"),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    rendered = environment.get_template(
        "report.md.jinja2", globals={"cell": _markdown_cell, "remaining": _remaining}
    ).render(context=build_markdown_context(report))
    return mdformat_text(rendered, extensions=["tables"])
