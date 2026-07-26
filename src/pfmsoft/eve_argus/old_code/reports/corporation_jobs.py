"""Report generation for corporation industry jobs."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel
from whenever import Instant

from esi_link import EsiLink
from esi_link.argus import requests
from esi_link.argus.calculations.industry_base_calculations import ActivityId
from esi_link.argus.models.esi_models import (
    GetCorporationsCorporationIdIndustryJobs,
    GetCorporationsCorporationIdIndustryJobsItem,
)


@dataclass(slots=True, kw_only=True)
class CorporationJobsResolvedItem:
    """A resolved item for a corporation's industry job.

    id fields are resolved to their names for easier readability.
    The original item is still available as the `item` attribute for reference.
    Data that is not resolved or transformed is left as-is in the `item` attribute.
    """

    activity: str
    blueprint_location: str
    blueprint: str
    completed_character: str | None
    facility: str
    installer: str
    location: str
    output_location: str
    product: str | None

    item: GetCorporationsCorporationIdIndustryJobsItem


class CorporationJobsResolved(BaseModel):
    corporation_id: int
    name: str
    """The name of the corporation."""
    date: str
    """The date the report was generated. This is a string in ISO 8601 format."""
    jobs: list[CorporationJobsResolvedItem] = []


SummaryGroup = Literal["manufacturing", "research", "reactions", "other"]


def _activity_group(activity_id: int) -> SummaryGroup:
    """Map an activity ID to a high-level summary group."""
    if activity_id == ActivityId.MANUFACTURING.value:
        return "manufacturing"
    if activity_id in {
        ActivityId.RESEARCHING_TIME_EFFICIENCY.value,
        ActivityId.RESEARCHING_MATERIAL_EFFICIENCY.value,
        ActivityId.COPYING.value,
        ActivityId.INVENTION.value,
    }:
        return "research"
    if activity_id == ActivityId.REACTIONS.value:
        return "reactions"
    return "other"


def _is_completed(job: GetCorporationsCorporationIdIndustryJobsItem) -> bool:
    """Determine if a job should be counted as completed in summary views."""
    if job.completed_date is not None:
        return True
    return job.status in {"delivered", "cancelled", "reverted"}


def _is_ready(job: GetCorporationsCorporationIdIndustryJobsItem) -> bool:
    """Determine if a job should be counted as ready in summary views."""
    end_date = Instant.parse_iso(job.end_date)
    now = Instant.now()
    if end_date < now and job.status == "active":
        return True
    return False


def _is_active(job: GetCorporationsCorporationIdIndustryJobsItem) -> bool:
    """Determine if a job should be counted as active in summary views."""
    return job.status == "active"


def _seconds_to_human(seconds: int) -> str:
    """Convert seconds to a compact human readable duration string."""
    if seconds <= 0:
        return "0m"

    days, remainder = divmod(seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, _ = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)


def _job_runtime_display(job: GetCorporationsCorporationIdIndustryJobsItem) -> str:
    """Return status display text for the job details table."""
    if _is_completed(job):
        return "COMPLETED"
    if job.status == "paused":
        return "PAUSED"
    if job.status != "active":
        return job.status.upper()

    now = Instant.now()
    end_at = Instant.parse_iso(job.end_date)
    remaining_seconds = int((end_at - now).total("seconds"))
    return _seconds_to_human(remaining_seconds)


def _safe_markdown_cell(value: str | None) -> str:
    """Escape markdown table delimiters and replace missing values."""
    if value is None or value == "":
        return "-"
    return value.replace("|", "\\|")


# TODO refactor this such that the necessary names are passed in as arguments instead of making API calls within the report generation function. This will make it easier to test and reuse the report generation logic with different data sources.
async def resolve_corporation_jobs(
    corp_jobs: GetCorporationsCorporationIdIndustryJobs, esi_link: EsiLink
) -> CorporationJobsResolved:
    """Generates a report of a corporation's industry jobs.

    Resolves all relevant IDs to their names for easier readability in the report.
    Dates are converted to ISO 8601 format for consistency and easier parsing.

    Args:
        corp_jobs: The corporation's industry jobs data from the ESI API.
        esi_link: An instance of EsiLink to use for API calls.

    Returns:
        A CorporationJobsReport containing the corporation's industry jobs.
    """
    ids_to_resolve = get_ids_from_corporation_jobs(corp_jobs)
    names = await requests.names_from_ids(ids_=ids_to_resolve, esi_link=esi_link)
    report_items: list[CorporationJobsResolvedItem] = []
    for job in corp_jobs.jobs:
        completed_character = (
            names.name(job.completed_character_id)
            if job.completed_character_id
            else None
        )
        report_item = CorporationJobsResolvedItem(
            activity=ActivityId(job.activity_id).name,
            blueprint_location=names.name(job.blueprint_location_id),
            blueprint=names.name(job.blueprint_type_id),
            completed_character=completed_character,
            facility=names.name(job.facility_id),
            installer=names.name(job.installer_id),
            location=names.name(job.location_id),
            output_location=names.name(job.output_location_id),
            product=names.name(job.product_type_id) if job.product_type_id else None,
            item=job,
        )
        report_items.append(report_item)
    report = CorporationJobsResolved(
        corporation_id=corp_jobs.corporation_id,
        name=names.name(corp_jobs.corporation_id),
        date=Instant.now().format_iso(),
        jobs=report_items,
    )
    return report


def get_ids_from_corporation_jobs(
    jobs: GetCorporationsCorporationIdIndustryJobs,
) -> set[int]:
    """Extracts all unique IDs from a GetCorporationsCorporationIdIndustryJobs response.

    Filters out invalid IDs (zero or negative values) that could cause API errors.
    """
    ids: set[int] = set()

    # Helper function to safely add IDs
    def add_id(id_value: int | None) -> None:
        if id_value is not None and id_value > 0:
            ids.add(id_value)

    # Add corporation ID if valid
    add_id(jobs.corporation_id)

    for job in jobs.jobs:
        # Add all IDs with validation
        add_id(job.blueprint_location_id)
        add_id(job.blueprint_type_id)
        add_id(job.completed_character_id)
        add_id(job.facility_id)
        add_id(job.installer_id)
        add_id(job.location_id)
        add_id(job.output_location_id)
        add_id(job.product_type_id)

    return ids


def generate_corporation_jobs_report(resolved_jobs: CorporationJobsResolved) -> str:
    """Generates a human-readable report of a corporation's industry jobs.

    Args:
        resolved_jobs: The resolved corporation jobs data.

    Returns:
        A string representing the human-readable report.
    """
    summary: dict[str, dict[str, dict[str, int]]] = {}
    for resolved_item in resolved_jobs.jobs:
        installer = resolved_item.installer
        if installer not in summary:
            summary[installer] = {
                "manufacturing": {
                    "total": 0,
                    "completed": 0,
                    "ready": 0,
                    "active": 0,
                },
                "research": {
                    "total": 0,
                    "completed": 0,
                    "ready": 0,
                    "active": 0,
                },
                "reactions": {
                    "total": 0,
                    "completed": 0,
                    "ready": 0,
                    "active": 0,
                },
                "other": {
                    "total": 0,
                    "completed": 0,
                    "ready": 0,
                    "active": 0,
                },
            }

        group = _activity_group(resolved_item.item.activity_id)
        summary[installer][group]["total"] += 1
        if _is_completed(resolved_item.item):
            summary[installer][group]["completed"] += 1
        if _is_ready(resolved_item.item):
            summary[installer][group]["ready"] += 1
        if _is_active(resolved_item.item):
            summary[installer][group]["active"] += 1

    lines: list[str] = []
    lines.append(f"# Corporation Jobs Report - {resolved_jobs.date}")
    lines.append("")
    lines.append(f"Corporation: {_safe_markdown_cell(resolved_jobs.name)}")
    lines.append("")

    lines.append("## Character Summary")
    lines.append("")
    lines.append(
        "| Character | Manufacturing (T/C/R/A) | Research (T/C/R/A) | Reactions (T/C/R/A) | Total (T/C/R/A) |"
    )
    lines.append("|---|---:|---:|---:|---:|")

    for installer in sorted(summary.keys()):
        manufacturing = summary[installer]["manufacturing"]
        research = summary[installer]["research"]
        reactions = summary[installer]["reactions"]
        other = summary[installer]["other"]

        total = {
            "total": manufacturing["total"]
            + research["total"]
            + reactions["total"]
            + other["total"],
            "completed": manufacturing["completed"]
            + research["completed"]
            + reactions["completed"]
            + other["completed"],
            "ready": manufacturing["ready"]
            + research["ready"]
            + reactions["ready"]
            + other["ready"],
            "active": manufacturing["active"]
            + research["active"]
            + reactions["active"]
            + other["active"],
        }

        lines.append(
            "| "
            f"{_safe_markdown_cell(installer)} | "
            f"{manufacturing['total']}/{manufacturing['completed']}/{manufacturing['ready']}/{manufacturing['active']} | "
            f"{research['total']}/{research['completed']}/{research['ready']}/{research['active']} | "
            f"{reactions['total']}/{reactions['completed']}/{reactions['ready']}/{reactions['active']} | "
            f"{total['total']}/{total['completed']}/{total['ready']}/{total['active']} |"
        )

    lines.append("")
    lines.append("## Jobs")
    lines.append("")
    lines.append(
        "| Activity | Blueprint | Facility | Installer | Product | End Date | Status |"
    )
    lines.append("|---|---|---|---|---|---|---|")

    sorted_jobs = sorted(
        resolved_jobs.jobs,
        key=lambda job: Instant.parse_iso(job.item.end_date),
    )
    for resolved_item in sorted_jobs:
        lines.append(
            "| "
            f"{_safe_markdown_cell(resolved_item.activity)} | "
            f"{_safe_markdown_cell(resolved_item.blueprint)} | "
            f"{_safe_markdown_cell(resolved_item.facility)} | "
            f"{_safe_markdown_cell(resolved_item.installer)} | "
            f"{_safe_markdown_cell(resolved_item.product)} | "
            f"{_safe_markdown_cell(resolved_item.item.end_date)} | "
            f"{_safe_markdown_cell(_job_runtime_display(resolved_item.item))} |"
        )

    lines.append("")
    return "\n".join(lines)
