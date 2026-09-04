"""Proof script for the corporation industry jobs ESI response.

Loads the corporation industry jobs (an authorized endpoint), collects the IDs
referenced by the jobs, resolves universe names for those IDs, and builds a
named jobs report. Each step depends on the previous one, so all calls are
kept together in this script. Requires sample auth data from the dev secrets
directory; the script exits without loading data if none is available.
"""

import asyncio
from logging import getLogger
from time import perf_counter_ns
from uuid import UUID

from _shared import (
    PROOF_OUTPUT_DIR,
    create_resources,
    get_sample_auth_data,
    setup_logging,
)

from pfmsoft.eve_argus.data_loaders.esi_responses import EsiResponseLoader
from pfmsoft.eve_argus.models.esi import esi_response_models
from pfmsoft.eve_argus.reports.corp_industry_jobs import (
    CollectedIds,
    CollectedIdsRoot,
    CorporationIndustryJobsNamed,
    CorporationIndustryJobsNamedRoot,
    collect_ids_for_lookup,
    create_corporation_industry_jobs_named,
)
from pfmsoft.eve_argus.reports.corp_industry_jobs_markdown import (
    render_corporation_industry_jobs_markdown,
)

logger = getLogger(__name__)

CORPORATION_INDUSTRY_JOBS_FILENAME = (
    PROOF_OUTPUT_DIR / "corporation_industry_jobs_response.json"
)
CORPORATION_INDUSTRY_JOBS_IDS_FILENAME = (
    PROOF_OUTPUT_DIR / "corporation_industry_jobs_ids.json"
)
CORPORATION_INDUSTRY_JOBS_UNIVERSE_NAMES_FILENAME = (
    PROOF_OUTPUT_DIR / "corporation_industry_jobs_universe_names_response.json"
)
CORPORATION_INDUSTRY_JOBS_NAMED_FILENAME = (
    PROOF_OUTPUT_DIR / "corporation_industry_jobs_named.json"
)
CORPORATION_INDUSTRY_JOBS_NAMED_REPORT_FILENAME = (
    PROOF_OUTPUT_DIR / "corporation_industry_jobs_named_report.md"
)


async def prove_corporation_industry_jobs() -> None:
    """Prove loading corporation industry jobs and building a named report."""
    sample_auth_data = get_sample_auth_data()
    print(f"Using sample auth data: {sample_auth_data}")
    if sample_auth_data is None:
        print("No sample auth data available, skipping corporation industry jobs.")
        return

    async with create_resources() as resources:
        loader = EsiResponseLoader(
            esi_link=resources.esi_link, schema=resources.esi_schema
        )
        corporation_industry_jobs_response = await corporation_industry_jobs(
            loader=loader,
            corporation_id=sample_auth_data["corporation_id"],
            character_id=sample_auth_data["character_id"],
            credential_id=sample_auth_data["cred_id"],
        )
        corp_jobs_named = await corporation_industry_jobs_named(
            corporation_industry_jobs_response=corporation_industry_jobs_response,
            loader=loader,
        )
        print()
        root_model = CorporationIndustryJobsNamedRoot(root=corp_jobs_named)
        CORPORATION_INDUSTRY_JOBS_NAMED_FILENAME.write_text(
            root_model.model_dump_json(indent=2)
        )
        print(
            f"Saved corporation industry jobs named response to {CORPORATION_INDUSTRY_JOBS_NAMED_FILENAME}"
        )


async def corporation_industry_jobs(
    loader: EsiResponseLoader,
    corporation_id: int,
    character_id: int,
    credential_id: UUID,
) -> esi_response_models.GetCorporationsCorporationIdIndustryJobsResponse:
    """Loads the corporation industry jobs from ESI."""
    print()
    start_time = perf_counter_ns()
    corporation_industry_jobs_response = await loader.corporation_industry_jobs(
        corporation_id=corporation_id,
        character_id=character_id,
        credential_id=credential_id,
    )
    end_time = perf_counter_ns()
    filename = CORPORATION_INDUSTRY_JOBS_FILENAME
    filename.write_text(corporation_industry_jobs_response.serialize(indent=2))
    print(f"Saved corporation industry jobs response to {filename}")
    print(
        f"Time taken to load corporation industry jobs: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
    )
    print(
        f"Loaded {len(corporation_industry_jobs_response.response_data.industry_jobs)} corporation industry jobs."
    )
    return corporation_industry_jobs_response


async def corporation_industry_jobs_named(
    corporation_industry_jobs_response: esi_response_models.GetCorporationsCorporationIdIndustryJobsResponse,
    loader: EsiResponseLoader,
) -> CorporationIndustryJobsNamed:
    """Builds the named corporation industry jobs and renders the report."""
    corp_jobs_ids = collect_corporation_industry_jobs_ids(
        corporation_industry_jobs_response
    )
    corp_jobs_universe_names = await corporation_industry_jobs_universe_names(
        corp_jobs_ids=corp_jobs_ids.universe_ids, loader=loader
    )
    corp_jobs_names_dict = {
        name.id: name.name for name in corp_jobs_universe_names.response_data.names
    }

    corp_jobs_named = create_corporation_industry_jobs_named(
        jobs=corporation_industry_jobs_response.response_data,
        names=corp_jobs_names_dict,
    )
    report = render_corporation_industry_jobs_markdown(corp_jobs_named)
    CORPORATION_INDUSTRY_JOBS_NAMED_REPORT_FILENAME.write_text(report)
    print(
        f"Saved corporation industry jobs named report to {CORPORATION_INDUSTRY_JOBS_NAMED_REPORT_FILENAME}"
    )
    return corp_jobs_named


async def corporation_industry_jobs_universe_names(
    corp_jobs_ids: set[int], loader: EsiResponseLoader
) -> esi_response_models.PostUniverseNamesResponse:
    """Loads the universe names for the given corporation industry jobs IDs from ESI."""
    print()
    start_time = perf_counter_ns()
    universe_names_response = await loader.universe_names(ids=corp_jobs_ids)
    end_time = perf_counter_ns()
    CORPORATION_INDUSTRY_JOBS_UNIVERSE_NAMES_FILENAME.write_text(
        universe_names_response.serialize(indent=2)
    )
    print(
        f"Saved corporation industry jobs universe names response to {CORPORATION_INDUSTRY_JOBS_UNIVERSE_NAMES_FILENAME}"
    )
    print(
        f"Time taken to load corporation industry jobs universe names: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
    )
    return universe_names_response


def collect_corporation_industry_jobs_ids(
    corporation_industry_jobs_response: esi_response_models.GetCorporationsCorporationIdIndustryJobsResponse,
) -> CollectedIds:
    """Loads and collects the IDs for corporation industry jobs from the given response."""
    print()
    collected_ids = collect_ids_for_lookup(
        corporation_industry_jobs_response.response_data
    )
    print(
        f"Found {len(collected_ids.universe_ids)} universe IDs and {len(collected_ids.corporation_ids)} corporation IDs."
    )
    CORPORATION_INDUSTRY_JOBS_IDS_FILENAME.write_text(
        CollectedIdsRoot(root=collected_ids).model_dump_json(indent=2)
    )
    return collected_ids


if __name__ == "__main__":
    log_filepath = setup_logging("corporation-industry-jobs")
    logger.info(f"Logging to {log_filepath}")
    asyncio.run(prove_corporation_industry_jobs())
