"""Fetch and update corporation blueprints when stored data expires."""

from dataclasses import dataclass
from sqlite3 import Connection
from uuid import UUID

from pfmsoft.eve_link import EsiLink, EsiSchema, FailedEsiResponse
from whenever import Instant

from pfmsoft.eve_argus.data_loaders import esi as FetchEsi
from pfmsoft.eve_argus.dynamic.access import DynamicDBReader, DynamicDBWriter
from pfmsoft.eve_argus.dynamic.db.models import CorporationBlueprintsResponse

_writer = DynamicDBWriter()
_reader = DynamicDBReader()


@dataclass(slots=True, kw_only=True)
class CorporationBlueprintsStatus:
    exists: bool
    expired: bool
    current_state: CorporationBlueprintsResponse | None


@dataclass(slots=True, kw_only=True)
class CorporationBlueprintsUpdateResult:
    update_successful: bool
    update_not_required: bool
    failure_message: str | None
    previous_state: CorporationBlueprintsResponse | None
    new_state: CorporationBlueprintsResponse | None


def _current_state(
    connection: Connection, *, corporation_id: int
) -> CorporationBlueprintsResponse | None:
    """Return the latest stored blueprints response for a corporation."""
    responses = _reader.read_corporation_blueprints_responses(
        connection, corporation_id=corporation_id
    )
    return responses[0] if responses else None


def _check_db_status(
    connection: Connection, *, corporation_id: int
) -> CorporationBlueprintsStatus:
    """Check whether the latest corporation blueprints response has expired."""
    current = _current_state(connection, corporation_id=corporation_id)
    expiration = (current.argus_expires_at or current.expires_at) if current else None
    expired = expiration is None or Instant.parse_iso(expiration) <= Instant.now()
    return CorporationBlueprintsStatus(
        exists=current is not None,
        expired=expired,
        current_state=current,
    )


async def _fetch_and_update_corporation_blueprints(
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: Connection,
    *,
    corporation_id: int,
    character_id: int,
    credential_id: UUID,
    current_state: CorporationBlueprintsResponse | None,
) -> CorporationBlueprintsUpdateResult:
    """Fetch and persist corporation blueprints, preserving previous state."""
    response = await FetchEsi.fetch_corporation_blueprints(
        esi_link,
        schema,
        corporation_id=corporation_id,
        character_id=character_id,
        credential_id=credential_id,
    )
    if isinstance(response, FailedEsiResponse):
        return CorporationBlueprintsUpdateResult(
            update_successful=False,
            update_not_required=False,
            failure_message=str(response.failed_response.error_messages),
            previous_state=current_state,
            new_state=None,
        )

    try:
        blueprints = FetchEsi.validate_corporation_blueprints(response)
        _writer.write_corporation_blueprints(connection, blueprints=blueprints)
        new_state = _current_state(connection, corporation_id=corporation_id)
    except Exception as error:
        return CorporationBlueprintsUpdateResult(
            update_successful=False,
            update_not_required=False,
            failure_message=str(error),
            previous_state=current_state,
            new_state=None,
        )

    return CorporationBlueprintsUpdateResult(
        update_successful=True,
        update_not_required=False,
        failure_message=None,
        previous_state=current_state,
        new_state=new_state,
    )


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
    status = _check_db_status(connection, corporation_id=corporation_id)
    if status.exists and not status.expired:
        return CorporationBlueprintsUpdateResult(
            update_successful=True,
            update_not_required=True,
            failure_message=None,
            previous_state=status.current_state,
            new_state=None,
        )

    return await _fetch_and_update_corporation_blueprints(
        esi_link,
        schema,
        connection,
        corporation_id=corporation_id,
        character_id=character_id,
        credential_id=credential_id,
        current_state=status.current_state,
    )
