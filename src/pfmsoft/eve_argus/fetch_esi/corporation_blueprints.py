"""Fetch and update corporation blueprints when stored data expires."""

from functools import partial
from sqlite3 import Connection
from uuid import UUID

from pfmsoft.eve_link import EsiLink, EsiResponse, EsiSchema

from pfmsoft.eve_argus.dynamic import read, write
from pfmsoft.eve_argus.dynamic.models import CorporationBlueprintsResponse
from pfmsoft.eve_argus.esi import fetch as EsiFetch
from pfmsoft.eve_argus.esi import validate as EsiValidate
from pfmsoft.eve_argus.fetch_esi.update import UpdateResult, update_if_expired

type CorporationBlueprintsUpdateResult = UpdateResult[CorporationBlueprintsResponse]


def _current_state(
    connection: Connection, *, corporation_id: int
) -> CorporationBlueprintsResponse | None:
    """Return the latest stored blueprints response for a corporation."""
    responses = read.corporation_blueprints_responses(
        connection, corporation_id=corporation_id
    )
    return responses[0] if responses else None


def _store(connection: Connection, response: EsiResponse) -> None:
    """Validate and write a blueprints response."""
    blueprints = EsiValidate.corporation_blueprints(response)
    write.corporation_blueprints(connection, blueprints=blueprints)


async def update_corporation_blueprints(
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: Connection,
    *,
    corporation_id: int,
    character_id: int,
    credential_id: UUID,
) -> CorporationBlueprintsUpdateResult:
    """Update corporation blueprints when their stored response has expired.

    Args:
        esi_link: ESI link instance.
        schema: ESI schema.
        connection: Dynamic database connection.
        corporation_id: Corporation whose blueprints are being updated.
        character_id: Character authorized to access the corporation endpoint.
        credential_id: ESI credential authorized for that character.
    """
    return await update_if_expired(
        read_current=partial(_current_state, connection, corporation_id=corporation_id),
        fetch=partial(
            EsiFetch.corporation_blueprints,
            esi_link,
            schema,
            corporation_id=corporation_id,
            character_id=character_id,
            credential_id=credential_id,
        ),
        store=partial(_store, connection),
    )
