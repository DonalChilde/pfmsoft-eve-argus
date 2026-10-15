"""Fetch and validate authorized corporation industry jobs, including completed jobs."""

from _shared import (
    create_resources,
    get_sample_auth_data,
    run_proof,
    save_raw_response,
    save_validated_response,
)

from pfmsoft.eve_argus.esi import fetch, validate


async def prove_corporation_industry_jobs() -> None:
    """Exercise the authorized jobs fetch using the development auth identity."""
    auth = get_sample_auth_data()
    async with create_resources() as resources:
        response = await fetch.corporation_industry_jobs(
            resources.esi_link,
            resources.esi_schema,
            corporation_id=auth.corporation_id,
            character_id=auth.character_id,
            credential_id=auth.credential_id,
        )
        response = save_raw_response(response, name="corporation-industry-jobs")
        save_validated_response(
            validate.corporation_industry_jobs(response),
            name="corporation-industry-jobs",
        )


if __name__ == "__main__":
    run_proof(prove_corporation_industry_jobs(), name="corporation-industry-jobs")
