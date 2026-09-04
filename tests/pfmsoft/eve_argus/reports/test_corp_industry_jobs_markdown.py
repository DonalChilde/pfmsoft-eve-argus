"""Tests for the corporation industry jobs Markdown report."""

from whenever import Instant

from pfmsoft.eve_argus.reports.corp_industry_jobs import (
    CorporationIndustryJobDetailedNamed,
    CorporationIndustryJobsNamed,
)
from pfmsoft.eve_argus.reports.corp_industry_jobs_markdown import (
    render_corporation_industry_jobs_markdown,
)

REPORT_TIME = Instant.parse_iso("2026-09-03T12:00:00Z")


def make_job(
    *,
    activity_id: int = 1,
    activity_name: str = "MANUFACTURING",
    status: str = "active",
    end_date: str = "2026-09-03T14:00:00Z",
    completed_date: str | None = None,
    pause_date: str | None = None,
    installer_id: int = 10,
    installer_name: str = "Ada Lovelace",
    blueprint_name: str = "Test Blueprint",
    completed_character_name: str | None = None,
    job_id: int = 1,
) -> CorporationIndustryJobDetailedNamed:
    """Build a job with sensible values for report tests."""
    return CorporationIndustryJobDetailedNamed(
        activity_id=activity_id,
        activity_name=activity_name,
        blueprint_id=job_id,
        blueprint_name=blueprint_name,
        blueprint_location_id=100,
        blueprint_location_name="Blueprint Hangar",
        blueprint_type_id=200,
        completed_character_id=None,
        completed_character_name=completed_character_name,
        completed_date=completed_date,
        cost=100.0,
        duration=7200,
        end_date=end_date,
        facility_id=300,
        facility_name="Test Facility",
        installer_id=installer_id,
        installer_name=installer_name,
        job_id=job_id,
        licensed_runs=None,
        location_id=400,
        location_name="Test Location",
        output_location_id=500,
        output_location_name="Output Hangar",
        pause_date=pause_date,
        probability=None,
        product_type_id=None,
        product_name=None,
        runs=1,
        start_date="2026-09-03T10:00:00Z",
        status=status,
        successful_runs=None,
    )


def render(*jobs: CorporationIndustryJobDetailedNamed) -> str:
    """Render test jobs at the fixed report timestamp."""
    return render_corporation_industry_jobs_markdown(
        CorporationIndustryJobsNamed(
            corporation_id=1,
            corporation_name="Test Corporation",
            industry_jobs=list(jobs),
        ),
        report_generated_at=REPORT_TIME,
    )


def test_report_includes_header_and_all_sections():
    """The report contains its header and all required sections."""
    report = render()

    assert "# Test Corporation Industry Jobs" in report
    assert "Generated at (UTC): `2026-09-03T12:00:00Z`" in report
    assert "## Character Summary" in report
    assert "## Active Jobs" in report
    assert "## Cancelled Jobs" in report
    assert "## Delivered Jobs" in report
    assert "## Paused Jobs" in report
    assert "## Ready Jobs" in report
    assert "## Reverted Jobs" in report


def test_report_places_paused_jobs_in_their_own_table():
    """Paused jobs appear in the paused table and not the active table."""
    report = render(
        make_job(status="paused", pause_date="2026-09-03T11:00:00Z"),
        make_job(
            job_id=2,
            blueprint_name="Running Blueprint",
            end_date="2026-09-03T16:00:00Z",
        ),
    )

    paused_section = report.split("## Paused Jobs", 1)[1].split("## Delivered Jobs", 1)[
        0
    ]
    active_section = report.split("## Active Jobs", 1)[1].split("## Paused Jobs", 1)[0]
    assert "Ada Lovelace" in paused_section
    assert "2026-09-03T11:00:00Z" in paused_section
    assert "Test Blueprint" not in active_section


def test_report_classifies_status_tables():
    """Jobs are separated into tables using their explicit status values."""
    report = render(
        make_job(status="active"),
        make_job(job_id=2, status="ready"),
        make_job(
            job_id=3,
            status="cancelled",
            end_date="2026-09-03T10:00:00Z",
        ),
    )

    assert report.count("Test Blueprint") == 3
    ready_section = report.split("## Ready Jobs", 1)[1].split("## Active Jobs", 1)[0]
    active_section = report.split("## Active Jobs", 1)[1].split("## Paused Jobs", 1)[0]
    cancelled_section = report.split("## Cancelled Jobs", 1)[1].split(
        "## Reverted Jobs", 1
    )[0]
    assert ready_section.count("Test Blueprint") == 1
    assert active_section.count("Test Blueprint") == 1
    assert cancelled_section.count("Test Blueprint") == 1


def test_delivered_table_includes_delivery_time_and_recipient():
    """Delivered rows keep facility, delivery time, and recipient columns aligned."""
    report = render(
        make_job(
            status="delivered",
            completed_date="2026-09-03T10:01:00Z",
            completed_character_name="Grace Hopper",
        )
    )

    assert (
        "| Ada Lovelace | MANUFACTURING | Test Blueprint | Blueprint Hangar | "
        "Output Hangar | Test Facility | "
        "2026-09-03T10:01:00Z | Grace Hopper |"
    ) in report


def test_character_summary_aggregates_research_activity_ids():
    """Research pool totals and status counts are rendered."""
    report = render(
        make_job(activity_id=1, status="ready"),
        make_job(
            activity_id=3,
            activity_name="RESEARCHING_TIME_EFFICIENCY",
            job_id=2,
            status="delivered",
        ),
        make_job(
            activity_id=4,
            activity_name="RESEARCHING_MATERIAL_EFFICIENCY",
            job_id=3,
            status="active",
        ),
        make_job(
            activity_id=5,
            activity_name="COPYING",
            job_id=4,
            status="paused",
        ),
        make_job(
            activity_id=8,
            activity_name="INVENTION",
            job_id=5,
            status="ready",
        ),
        make_job(activity_id=11, activity_name="REACTION", job_id=6),
    )

    assert "Manufacturing (T/A/R/P)" in report
    assert (
        "| Ada Lovelace | 1/0/1/0 | 3/1/1/1 | 1/0/0/1 | 1/0/1/0 | 1/1/0/0 | 0/0/0/0 | 1/1/0/0 |"
        in report
    )
