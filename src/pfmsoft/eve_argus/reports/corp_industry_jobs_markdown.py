"""Render corporation industry jobs as a Markdown report."""

from collections import defaultdict
from dataclasses import dataclass
from importlib.resources import files

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from whenever import Instant

from pfmsoft.eve_argus.models.esi.esi_response_models import (
    GetCorporationsCorporationIdIndustryJobsDetail_Status,
)
from pfmsoft.eve_argus.reports.corp_industry_jobs import (
    CorporationIndustryJobDetailedNamed,
    CorporationIndustryJobsNamed,
)

_ACTIVITY_CATEGORIES = {
    1: "manufacturing",
    3: "te",
    4: "me",
    5: "copying",
    8: "invention",
    11: "reactions",
}
_STATUS_TABLES = {
    status.value: status.name.title()
    for status in GetCorporationsCorporationIdIndustryJobsDetail_Status
}


@dataclass(frozen=True, slots=True)
class JobRow:
    """Template-ready values for one industry job."""

    job: CorporationIndustryJobDetailedNamed
    end_date: str
    completed_date: str | None
    pause_date: str | None
    remaining: str | None = None


@dataclass(frozen=True, slots=True)
class JobCounts:
    """Total, active, ready, and paused counts for one job category."""

    total: int
    active: int
    ready: int
    paused: int


@dataclass(frozen=True, slots=True)
class CharacterSummary:
    """Counts of industry jobs installed by one character."""

    installer_name: str
    manufacturing: JobCounts
    research: JobCounts
    copying: JobCounts
    invention: JobCounts
    me: JobCounts
    te: JobCounts
    reactions: JobCounts


@dataclass(frozen=True, slots=True)
class StatusTables:
    """Industry job rows grouped by status for the report templates."""

    active: list[JobRow]
    cancelled: list[JobRow]
    delivered: list[JobRow]
    paused: list[JobRow]
    ready: list[JobRow]
    reverted: list[JobRow]


@dataclass(frozen=True, slots=True)
class CorporationIndustryJobsContext:
    """Dataclass context supplied to the corporation industry jobs templates."""

    corporation: CorporationIndustryJobsNamed
    generated_at: str
    summaries: list[CharacterSummary]
    status_tables: StatusTables
    other_jobs: list[JobRow]


def _format_remaining(seconds: float) -> str:
    if seconds <= 0:
        return "Ready"

    total_seconds = int(seconds)
    days, remainder = divmod(total_seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, seconds = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def _job_row(job: CorporationIndustryJobDetailedNamed, report_time: Instant) -> JobRow:
    end_date = Instant.parse_iso(job.end_date)
    completed_date = (
        Instant.parse_iso(job.completed_date).format_iso()
        if job.completed_date
        else None
    )
    pause_date = (
        Instant.parse_iso(job.pause_date).format_iso() if job.pause_date else None
    )
    return JobRow(
        job=job,
        end_date=end_date.format_iso(),
        completed_date=completed_date,
        pause_date=pause_date,
        remaining=_format_remaining((end_date - report_time).total("seconds")),
    )


def _classify_jobs(
    jobs: list[CorporationIndustryJobDetailedNamed], report_time: Instant
) -> dict[str, list[JobRow]]:
    classified: dict[str, list[JobRow]] = defaultdict(list)
    for job in jobs:
        row = _job_row(job, report_time)
        group = job.status if job.status in _STATUS_TABLES else "other"
        classified[group].append(row)

    for rows in classified.values():
        rows.sort(key=lambda row: row.end_date)
    return classified


def _summarize_jobs(
    jobs: list[CorporationIndustryJobDetailedNamed],
    report_time: Instant,
) -> list[CharacterSummary]:
    grouped: dict[int, list[CorporationIndustryJobDetailedNamed]] = defaultdict(list)
    for job in jobs:
        grouped[job.installer_id].append(job)

    summaries: list[CharacterSummary] = []
    for character_jobs in grouped.values():
        counts: dict[str, JobCounts] = {}
        for job in character_jobs:
            category = _ACTIVITY_CATEGORIES.get(job.activity_id)
            if category is None:
                continue
            previous = counts.get(category, JobCounts(0, 0, 0, 0))
            active = previous.active + (job.status == "active")
            ready = previous.ready + (job.status == "ready")
            paused = previous.paused + (job.status == "paused")
            counts[category] = JobCounts(
                total=active + ready + paused,
                active=active,
                ready=ready,
                paused=paused,
            )

        research_categories = ("copying", "invention", "me", "te")
        research = JobCounts(
            total=sum(
                counts.get(category, JobCounts(0, 0, 0, 0)).total
                for category in research_categories
            ),
            ready=sum(
                counts.get(category, JobCounts(0, 0, 0, 0)).ready
                for category in research_categories
            ),
            active=sum(
                counts.get(category, JobCounts(0, 0, 0, 0)).active
                for category in research_categories
            ),
            paused=sum(
                counts.get(category, JobCounts(0, 0, 0, 0)).paused
                for category in research_categories
            ),
        )
        summaries.append(
            CharacterSummary(
                installer_name=character_jobs[0].installer_name,
                manufacturing=counts.get("manufacturing", JobCounts(0, 0, 0, 0)),
                research=research,
                copying=counts.get("copying", JobCounts(0, 0, 0, 0)),
                invention=counts.get("invention", JobCounts(0, 0, 0, 0)),
                me=counts.get("me", JobCounts(0, 0, 0, 0)),
                te=counts.get("te", JobCounts(0, 0, 0, 0)),
                reactions=counts.get("reactions", JobCounts(0, 0, 0, 0)),
            )
        )
    return sorted(summaries, key=lambda summary: summary.installer_name)


def render_corporation_industry_jobs_markdown(
    jobs: CorporationIndustryJobsNamed,
    *,
    report_generated_at: Instant | None = None,
) -> str:
    """Render corporation industry jobs as a Markdown report."""
    report_time = report_generated_at or Instant.now()
    classified = _classify_jobs(jobs.industry_jobs, report_time)
    context = CorporationIndustryJobsContext(
        corporation=jobs,
        generated_at=report_time.format_iso(),
        summaries=_summarize_jobs(jobs.industry_jobs, report_time),
        status_tables=StatusTables(
            active=classified.get("active", []),
            cancelled=classified.get("cancelled", []),
            delivered=classified.get("delivered", []),
            paused=classified.get("paused", []),
            ready=classified.get("ready", []),
            reverted=classified.get("reverted", []),
        ),
        other_jobs=classified.get("other", []),
    )
    template_root = files("pfmsoft.eve_argus.templates") / "corp_industry_jobs"
    environment = Environment(
        loader=FileSystemLoader(str(template_root)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return environment.get_template("base.md.jinja2").render(context=context)


__all__ = ["render_corporation_industry_jobs_markdown"]
