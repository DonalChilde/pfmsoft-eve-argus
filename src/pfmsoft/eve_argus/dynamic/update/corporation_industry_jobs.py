"""Fetch and update corporation industry jobs when stored data expires."""

from dataclasses import dataclass
from sqlite3 import Connection
from uuid import UUID

from pfmsoft.eve_link import EsiLink, EsiSchema, FailedEsiResponse
from whenever import Instant

from pfmsoft.eve_argus.data_loaders import esi as FetchEsi
from pfmsoft.eve_argus.dynamic.access import DynamicDBReader, DynamicDBWriter
from pfmsoft.eve_argus.dynamic.db.models import CorporationIndustryJobsResponse

_writer = DynamicDBWriter()
_reader = DynamicDBReader()


@dataclass(slots=True, kw_only=True)
class CorporationIndustryJobsStatus:
    exists: bool
    expired: bool
    current_state: CorporationIndustryJobsResponse | None


@dataclass(slots=True, kw_only=True)
class CorporationIndustryJobsUpdateResult:
    update_successful: bool
    update_not_required: bool
    failure_message: str | None
    previous_state: CorporationIndustryJobsResponse | None
    new_state: CorporationIndustryJobsResponse | None


def _current_state(
    connection: Connection, *, corporation_id: int
) -> CorporationIndustryJobsResponse | None:
    """Return the latest stored industry-jobs response for a corporation."""
    responses = _reader.read_corporation_industry_jobs_responses(
        connection, corporation_id=corporation_id
    )
    return responses[0] if responses else None


def _check_db_status(
    connection: Connection, *, corporation_id: int
) -> CorporationIndustryJobsStatus:
    """Check whether the latest corporation industry-jobs response has expired."""
    current = _current_state(connection, corporation_id=corporation_id)
    expiration = (current.argus_expires_at or current.expires_at) if current else None
    expired = expiration is None or Instant.parse_iso(expiration) <= Instant.now()
    return CorporationIndustryJobsStatus(
        exists=current is not None,
        expired=expired,
        current_state=current,
    )


async def _fetch_and_update_corporation_industry_jobs(
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: Connection,
    *,
    corporation_id: int,
    character_id: int,
    credential_id: UUID,
    current_state: CorporationIndustryJobsResponse | None,
) -> CorporationIndustryJobsUpdateResult:
    """Fetch and persist corporation jobs, preserving the previous state."""
    response = await FetchEsi.fetch_corporation_industry_jobs(
        esi_link,
        schema,
        corporation_id=corporation_id,
        character_id=character_id,
        credential_id=credential_id,
    )
    if isinstance(response, FailedEsiResponse):
        return CorporationIndustryJobsUpdateResult(
            update_successful=False,
            update_not_required=False,
            failure_message=str(response.failed_response.error_messages),
            previous_state=current_state,
            new_state=None,
        )

    try:
        jobs = FetchEsi.validate_corporation_industry_jobs(response)
        _writer.write_corporation_industry_jobs(connection, jobs=jobs)
        new_state = _current_state(connection, corporation_id=corporation_id)
    except Exception as error:
        return CorporationIndustryJobsUpdateResult(
            update_successful=False,
            update_not_required=False,
            failure_message=str(error),
            previous_state=current_state,
            new_state=None,
        )

    return CorporationIndustryJobsUpdateResult(
        update_successful=True,
        update_not_required=False,
        failure_message=None,
        previous_state=current_state,
        new_state=new_state,
    )


async def update_corporation_industry_jobs(
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: Connection,
    *,
    corporation_id: int,
    character_id: int,
    credential_id: UUID,
) -> CorporationIndustryJobsUpdateResult:
    """Update corporation industry jobs when their stored response has expired.

    Args:
        esi_link: ESI link instance.
        schema: ESI schema.
        connection: Dynamic database connection.
        corporation_id: Corporation whose jobs are being updated.
        character_id: Character authorized to access the corporation endpoint.
        credential_id: ESI credential authorized for that character.
    """
    status = _check_db_status(connection, corporation_id=corporation_id)
    if status.exists and not status.expired:
        return CorporationIndustryJobsUpdateResult(
            update_successful=True,
            update_not_required=True,
            failure_message=None,
            previous_state=status.current_state,
            new_state=None,
        )

    return await _fetch_and_update_corporation_industry_jobs(
        esi_link,
        schema,
        connection,
        corporation_id=corporation_id,
        character_id=character_id,
        credential_id=credential_id,
        current_state=status.current_state,
    )
