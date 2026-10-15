"""Fetch and validate authorized corporation blueprints using the new ESI package."""

from _shared import (
    create_resources,
    get_sample_auth_data,
    run_proof,
    save_raw_response,
    save_validated_response,
)

from pfmsoft.eve_argus.esi import fetch, validate


async def prove_corporation_blueprints() -> None:
    """Exercise the authorized blueprint fetch without building unrelated reports."""
    auth = get_sample_auth_data()
    async with create_resources() as resources:
        response = await fetch.corporation_blueprints(
            resources.esi_link,
            resources.esi_schema,
            corporation_id=auth.corporation_id,
            character_id=auth.character_id,
            credential_id=auth.credential_id,
        )
        response = save_raw_response(response, name="corporation-blueprints")
        save_validated_response(
            validate.corporation_blueprints(response), name="corporation-blueprints"
        )


if __name__ == "__main__":
    run_proof(prove_corporation_blueprints(), name="corporation-blueprints")
