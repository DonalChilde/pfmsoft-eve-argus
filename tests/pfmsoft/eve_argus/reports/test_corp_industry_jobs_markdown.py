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
        completed_character_name=None,
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
    assert "## Ready Jobs" in report
    assert "## Running Jobs" in report
    assert "## Paused Jobs" in report
    assert "## Completed Jobs" in report


def test_report_places_paused_jobs_in_their_own_table():
    """Paused jobs appear in the paused table and not the running table."""
    report = render(
        make_job(status="paused", pause_date="2026-09-03T11:00:00Z"),
        make_job(
            job_id=2,
            blueprint_name="Running Blueprint",
            end_date="2026-09-03T16:00:00Z",
        ),
    )

    paused_section = report.split("## Paused Jobs", 1)[1].split("## Completed Jobs", 1)[
        0
    ]
    running_section = report.split("## Running Jobs", 1)[1].split("## Paused Jobs", 1)[
        0
    ]
    assert "Ada Lovelace" in paused_section
    assert "2026-09-03T11:00:00Z" in paused_section
    assert "Test Blueprint" not in running_section


def test_report_classifies_ready_running_and_completed_jobs():
    """Jobs are separated by status and the report time boundary."""
    report = render(
        make_job(end_date="2026-09-03T12:00:00Z"),
        make_job(job_id=2, end_date="2026-09-03T14:30:00Z"),
        make_job(
            job_id=3,
            status="completed",
            end_date="2026-09-03T10:00:00Z",
            completed_date="2026-09-03T10:01:00Z",
        ),
    )

    assert report.count("Test Blueprint") == 3
    assert "2h 30m" in report
    ready_section = report.split("## Ready Jobs", 1)[1].split("## Running Jobs", 1)[0]
    running_section = report.split("## Running Jobs", 1)[1].split("## Paused Jobs", 1)[
        0
    ]
    completed_section = report.split("## Completed Jobs", 1)[1]
    assert ready_section.count("Test Blueprint") == 1
    assert running_section.count("Test Blueprint") == 1
    assert completed_section.count("Test Blueprint") == 1


def test_character_summary_aggregates_research_activity_ids():
    """Research pool totals and per-activity ready counts are rendered."""
    report = render(
        make_job(activity_id=1, end_date="2026-09-03T12:00:00Z"),
        make_job(
            activity_id=3,
            activity_name="RESEARCHING_TIME_EFFICIENCY",
            job_id=2,
            status="completed",
        ),
        make_job(
            activity_id=4,
            activity_name="RESEARCHING_MATERIAL_EFFICIENCY",
            job_id=3,
        ),
        make_job(
            activity_id=5,
            activity_name="COPYING",
            job_id=4,
            status="completed",
        ),
        make_job(activity_id=8, activity_name="INVENTION", job_id=5),
        make_job(activity_id=11, activity_name="REACTION", job_id=6),
    )

    assert "Manufacturing (total/ready)" in report
    assert "| Ada Lovelace | 1/1 | 4/0 | 1/0 | 1/0 | 1/0 | 1/0 | 1/0 |" in report
