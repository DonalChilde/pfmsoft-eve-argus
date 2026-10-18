"""Collect database-independent data for corporation industry job reports."""

import logging
from dataclasses import asdict, dataclass
from math import ceil

from pfmsoft.eve_link import EsiLink, EsiResponse, EsiSchema, FailedEsiResponse
from whenever import Instant

from pfmsoft.eve_argus.dynamic.models import (
    CorporationIndustryJobRow,
    CorporationIndustryJobsDataset,
    ResponseMetadata,
)
from pfmsoft.eve_argus.esi import fetch, validate
from pfmsoft.eve_argus.esi.models import (
    PostUniverseNamesCategory,
    PostUniverseNamesDetail,
)
from pfmsoft.eve_argus.static.models import (
    IndustryActivitiesDataset,
    MarketGroupsDataset,
    TypesDataset,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True, kw_only=True, frozen=True)
class CorporationJobReportRow(CorporationIndustryJobRow):
    """Original job values with names and status derived at report generation time."""

    activity_name: str
    blueprint_name: str
    blueprint_market_group_id: int | None
    blueprint_market_path: tuple[str, ...] | None
    blueprint_location_name: str
    completed_character_name: str | None
    facility_name: str
    installer_name: str
    location_name: str
    output_location_name: str
    product_name: str | None
    effective_status: str
    remaining_seconds: int | None


@dataclass(slots=True, kw_only=True, frozen=True)
class CorporationJobsReport(ResponseMetadata):
    """Collected report shared by all renderers; costs retain Decimal precision.

    is_stale is unknown (None) when neither source expiration is available.
    argus_expires_at takes precedence over expires_at for freshness.
    """

    corporation_id: int
    corporation_name: str
    generated_at: str
    is_stale: bool | None
    jobs: tuple[CorporationJobReportRow, ...]
    warnings: tuple[str, ...]


def collect_universe_name_ids(jobs: CorporationIndustryJobsDataset) -> set[int]:
    """Collect public identity and location candidates for universe-name lookup.

    Type and activity names come from static datasets. Blueprint item IDs, job IDs,
    local response IDs, and private blueprint/output locations are not public name
    identifiers, even if their integer values happen to resolve to something else.

    Facilities and installation locations can be public stations or private structures.
    Exclude values outside the endpoint's positive int32 range. Being in range is only
    a prerequisite: callers must still check ESI failures and returned categories.
    Unsupported location names will be represented as UNKNOWN by the report collector.

    Args:
        jobs: A single corporation's stored industry jobs snapshot.

    Returns:
        Deduplicated IDs for corporation/character identities and eligible locations.
    """
    ids = {jobs.corporation_id}
    for job in jobs.records.values():
        ids.add(job.installer_id)
        if job.completed_character_id is not None:
            ids.add(job.completed_character_id)
        ids.update(
            location_id
            for location_id in (job.facility_id, job.location_id)
            if 0 < location_id <= 2**31 - 1
        )
    return ids


def _identity_name(
    names: dict[int, PostUniverseNamesDetail],
    *,
    identity_id: int,
    category: PostUniverseNamesCategory,
) -> str:
    record = names.get(identity_id)
    if record is None or record.category != category:
        raise ValueError(
            f"Expected universe name for {category.value} {identity_id}; got {record!r}"
        )
    return record.name


def _location_name(
    names: dict[int, PostUniverseNamesDetail],
    *,
    location_id: int,
    warnings: set[str],
) -> str:
    record = names.get(location_id)
    if record is None:
        warnings.add(
            f"Location {location_id}: UNKNOWN; private or unresolved location names "
            "are not available in this report."
        )
        return "UNKNOWN"
    if record.category != PostUniverseNamesCategory.STATION:
        raise ValueError(
            f"Expected station name for location {location_id}; got {record.category}"
        )
    return record.name


async def collect_corporation_jobs_report(
    *,
    jobs: CorporationIndustryJobsDataset,
    types: TypesDataset,
    market_groups: MarketGroupsDataset,
    industry_activities: IndustryActivitiesDataset,
    esi_link: EsiLink,
    schema: EsiSchema,
    generated_at: Instant,
) -> CorporationJobsReport:
    """Enrich one stored snapshot without accessing databases or writing files.

    The caller selects and loads the snapshot and static datasets, including
    unpublished types. All derived statuses/countdowns use generated_at; raw
    timestamps and status remain unchanged. Only public names require network I/O.
    Private blueprint/output location names are always UNKNOWN for this version.

    Raises:
        RuntimeError: If any universe-name request fails or returns no batches.
        ValueError: If names have unexpected categories, required identities/static
            references are absent, source rows disagree with the snapshot, or
            timestamps/ESI response data are invalid.
    """
    ids = collect_universe_name_ids(jobs)
    responses = await fetch.universe_names(esi_link, schema, ids=ids)
    successful: list[EsiResponse] = []
    for response in responses:
        if isinstance(response, FailedEsiResponse):
            raise RuntimeError(
                "Universe-name lookup failed: "
                + "; ".join(response.failed_response.error_messages)
            )
        successful.append(response)
    if not successful:
        raise RuntimeError("Universe-name lookup returned no response batches.")
    names: dict[int, PostUniverseNamesDetail] = {}
    for record in validate.universe_names(successful).names:
        if record.id not in ids:
            # Never use unrelated response records to dereference private item IDs
            # or other local namespaces.
            continue
        if record.id in names and names[record.id] != record:
            raise ValueError(f"Conflicting universe names for ID {record.id}.")
        names[record.id] = record
    corporation_name = _identity_name(
        names,
        identity_id=jobs.corporation_id,
        category=PostUniverseNamesCategory.CORPORATION,
    )
    warnings: set[str] = set()
    rows: list[CorporationJobReportRow] = []
    for job in sorted(jobs.records.values(), key=lambda job: job.job_id):
        if (
            job.corporation_id != jobs.corporation_id
            or job.response_metadata_id != jobs.response_metadata_id
        ):
            raise ValueError(f"Job {job.job_id} does not belong to this snapshot.")
        blueprint = types.get(job.blueprint_type_id)
        if blueprint is None:
            raise ValueError(f"Missing static blueprint type {job.blueprint_type_id}.")
        product = (
            types.get(job.product_type_id) if job.product_type_id is not None else None
        )
        if job.product_type_id is not None and product is None:
            raise ValueError(f"Missing static product type {job.product_type_id}.")
        activity = industry_activities.get(job.activity_id)
        if activity is None:
            raise ValueError(f"Missing static industry activity {job.activity_id}.")
        market_group = (
            market_groups.get(blueprint.market_group_id)
            if blueprint.market_group_id is not None
            else None
        )
        if blueprint.market_group_id is not None and market_group is None:
            raise ValueError(
                f"Missing static market group {blueprint.market_group_id}."
            )
        end = Instant.parse_iso(job.end_date)
        effective_status = (
            "ready" if job.status == "active" and end <= generated_at else job.status
        )
        remaining = (
            ceil((end - generated_at).total("seconds"))
            if effective_status == "active"
            else None
        )
        for private_id in {job.blueprint_location_id, job.output_location_id}:
            warnings.add(
                f"Location {private_id}: UNKNOWN; private or unresolved location names "
                "are not available in this report."
            )
        rows.append(
            CorporationJobReportRow(
                **asdict(job),
                activity_name=activity.name,
                blueprint_name=blueprint.name,
                blueprint_market_group_id=blueprint.market_group_id,
                blueprint_market_path=market_group.str_path if market_group else None,
                blueprint_location_name="UNKNOWN",
                completed_character_name=(
                    _identity_name(
                        names,
                        identity_id=job.completed_character_id,
                        category=PostUniverseNamesCategory.CHARACTER,
                    )
                    if job.completed_character_id is not None
                    else None
                ),
                facility_name=_location_name(
                    names,
                    location_id=job.facility_id,
                    warnings=warnings,
                ),
                installer_name=_identity_name(
                    names,
                    identity_id=job.installer_id,
                    category=PostUniverseNamesCategory.CHARACTER,
                ),
                location_name=_location_name(
                    names,
                    location_id=job.location_id,
                    warnings=warnings,
                ),
                output_location_name="UNKNOWN",
                product_name=product.name if product else None,
                effective_status=effective_status,
                remaining_seconds=remaining,
            )
        )
    Instant.parse_iso(jobs.received_at)
    for expiration in (jobs.expires_at, jobs.argus_expires_at):
        if expiration is not None:
            Instant.parse_iso(expiration)
    effective_expiry = jobs.argus_expires_at or jobs.expires_at
    for warning in sorted(warnings):
        logger.warning("%s", warning)
    return CorporationJobsReport(
        response_metadata_id=jobs.response_metadata_id,
        received_at=jobs.received_at,
        expires_at=jobs.expires_at,
        argus_expires_at=jobs.argus_expires_at,
        corporation_id=jobs.corporation_id,
        corporation_name=corporation_name,
        generated_at=generated_at.format_iso(),
        is_stale=(
            Instant.parse_iso(effective_expiry) <= generated_at
            if effective_expiry is not None
            else None
        ),
        jobs=tuple(rows),
        warnings=tuple(sorted(warnings)),
    )
