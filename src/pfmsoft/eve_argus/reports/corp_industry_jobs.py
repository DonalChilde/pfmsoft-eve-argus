from dataclasses import dataclass, field

from pydantic import RootModel

from pfmsoft.eve_argus.calculations.industry_base_calculations import ActivityId
from pfmsoft.eve_argus.models.esi.esi_response_models import (
    GetCorporationsCorporationIdIndustryJobs,
)


@dataclass(slots=True, kw_only=True)
class CorporationIndustryJobDetailedNamed:
    activity_id: int
    activity_name: str
    blueprint_id: int
    blueprint_name: str
    blueprint_location_id: int
    blueprint_location_name: str
    blueprint_type_id: int
    blueprint_name: str
    completed_character_id: int | None = None
    completed_character_name: str | None = None
    completed_date: str | None = None
    cost: float | None = None
    duration: int
    end_date: str
    facility_id: int
    facility_name: str
    installer_id: int
    installer_name: str
    job_id: int
    licensed_runs: int | None = None
    location_id: int
    location_name: str
    output_location_id: int
    output_location_name: str
    pause_date: str | None = None
    probability: float | None = None
    product_type_id: int | None = None
    product_name: str | None = None
    runs: int
    start_date: str
    status: str
    successful_runs: int | None = None


@dataclass
class CorporationIndustryJobsNamed:
    corporation_id: int
    corporation_name: str
    industry_jobs: list[CorporationIndustryJobDetailedNamed]


CorporationIndustryJobsNamedRoot = RootModel[CorporationIndustryJobsNamed]


def create_corporation_industry_jobs_named(
    jobs: GetCorporationsCorporationIdIndustryJobs, names: dict[int, str]
) -> CorporationIndustryJobsNamed:
    """Create a CorporationIndustryJobsNamed instance from raw industry jobs and a names dictionary."""
    NOT_FOUND = "Unknown"
    corporation_name = names.get(jobs.corporation_id, NOT_FOUND)
    industry_jobs_named = [
        CorporationIndustryJobDetailedNamed(
            activity_id=job.activity_id,
            activity_name=ActivityId(job.activity_id).name,
            blueprint_id=job.blueprint_id,
            blueprint_location_id=job.blueprint_location_id,
            blueprint_location_name=names.get(job.blueprint_location_id, NOT_FOUND),
            blueprint_type_id=job.blueprint_type_id,
            blueprint_name=names.get(job.blueprint_type_id, NOT_FOUND),
            completed_character_id=job.completed_character_id,
            completed_character_name=names.get(job.completed_character_id, NOT_FOUND)
            if job.completed_character_id
            else None,
            completed_date=job.completed_date,
            cost=job.cost,
            duration=job.duration,
            end_date=job.end_date,
            facility_id=job.facility_id,
            facility_name=names.get(job.facility_id, NOT_FOUND),
            installer_id=job.installer_id,
            installer_name=names.get(job.installer_id, NOT_FOUND),
            job_id=job.job_id,
            licensed_runs=job.licensed_runs,
            location_id=job.location_id,
            location_name=names.get(job.location_id, NOT_FOUND),
            output_location_id=job.output_location_id,
            output_location_name=names.get(job.output_location_id, NOT_FOUND),
            pause_date=job.pause_date,
            probability=job.probability,
            product_type_id=job.product_type_id,
            product_name=names.get(job.product_type_id, NOT_FOUND)
            if job.product_type_id
            else None,
            runs=job.runs,
            start_date=job.start_date,
            status=job.status,
            successful_runs=job.successful_runs,
        )
        for job in jobs.industry_jobs
    ]

    return CorporationIndustryJobsNamed(
        corporation_id=jobs.corporation_id,
        corporation_name=corporation_name,
        industry_jobs=industry_jobs_named,
    )


@dataclass(slots=True, kw_only=True)
class CollectedIds:
    universe_ids: set[int] = field(default_factory=set[int])
    corporation_ids: set[int] = field(default_factory=set[int])


CollectedIdsRoot = RootModel[CollectedIds]


def collect_ids_for_lookup(
    jobs: GetCorporationsCorporationIdIndustryJobs,
) -> CollectedIds:
    """Collects all relevant universe and corporation IDs from the given industry jobs for lookup purposes.

    universe_ids are valid id for the PostUniverse lookup.
    Ids that are private to a corporation, like hangar locations, are collected under corporation_ids.
    """
    collected_ids = CollectedIds()
    collected_ids.universe_ids.add(jobs.corporation_id)
    for job in jobs.industry_jobs:
        collected_ids.corporation_ids.add(job.blueprint_location_id)
        collected_ids.universe_ids.add(job.blueprint_type_id)
        if job.completed_character_id:
            collected_ids.universe_ids.add(job.completed_character_id)
        collected_ids.universe_ids.add(job.facility_id)
        collected_ids.universe_ids.add(job.installer_id)
        collected_ids.universe_ids.add(job.location_id)
        collected_ids.corporation_ids.add(job.output_location_id)
        if job.product_type_id:
            collected_ids.universe_ids.add(job.product_type_id)
    return collected_ids
