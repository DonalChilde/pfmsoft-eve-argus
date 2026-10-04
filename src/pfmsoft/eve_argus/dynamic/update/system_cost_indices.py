"""Fetch and update system cost indices when stored data expires."""

import logging
from dataclasses import dataclass
from sqlite3 import Connection

from pfmsoft.eve_link import (
    EsiLink,
    EsiSchema,
    FailedEsiResponse,
)
from whenever import Instant

from pfmsoft.eve_argus.data_loaders import esi as FetchEsi
from pfmsoft.eve_argus.dynamic.access import DynamicDBReader, DynamicDBWriter
from pfmsoft.eve_argus.dynamic.db.models import SystemCostIndicesResponse

logger = logging.getLogger(__name__)
_writer = DynamicDBWriter()
_reader = DynamicDBReader()


@dataclass(slots=True, kw_only=True)
class SystemCostIndicesStatus:
    exists: bool
    expired: bool
    current_state: SystemCostIndicesResponse | None


@dataclass(slots=True, kw_only=True)
class SystemCostIndicesUpdateResult:
    update_successful: bool
    update_not_required: bool
    failure_message: str | None
    previous_state: SystemCostIndicesResponse | None
    new_state: SystemCostIndicesResponse | None


async def _fetch_and_update_system_cost_indices(
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: Connection,
    current_state: SystemCostIndicesResponse | None,
) -> SystemCostIndicesUpdateResult:
    """Fetch and persist system cost indices, preserving the previous state."""
    response = await FetchEsi.fetch_system_cost_indices(esi_link, schema)
    if isinstance(response, FailedEsiResponse):
        return SystemCostIndicesUpdateResult(
            update_successful=False,
            update_not_required=False,
            failure_message=str(response.failed_response.error_messages),
            previous_state=current_state,
            new_state=None,
        )

    try:
        system_cost_indices = FetchEsi.validate_system_cost_indices(response)
        _writer.write_system_cost_indices(
            connection, system_cost_indices=system_cost_indices
        )
        new_state = _current_state(connection)
    except Exception as error:
        return SystemCostIndicesUpdateResult(
            update_successful=False,
            update_not_required=False,
            failure_message=str(error),
            previous_state=current_state,
            new_state=None,
        )

    return SystemCostIndicesUpdateResult(
        update_successful=True,
        update_not_required=False,
        failure_message=None,
        previous_state=current_state,
        new_state=new_state,
    )


def _current_state(conn: Connection) -> SystemCostIndicesResponse | None:
    responses = _reader.read_system_cost_indices_responses(conn)
    return responses[0] if responses else None


def _check_db_status(conn: Connection) -> SystemCostIndicesStatus:
    """Check whether the latest system cost indices response is expired."""
    current = _current_state(conn)
    now = Instant.now()
    exists = current is not None
    expiration = (current.argus_expires_at or current.expires_at) if current else None
    expired = not exists or expiration is None or Instant.parse_iso(expiration) <= now
    return SystemCostIndicesStatus(
        exists=exists,
        expired=expired,
        current_state=current,
    )


async def update_system_cost_indices(
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: Connection,
) -> SystemCostIndicesUpdateResult:
    """Update system cost indices when the stored response has expired."""
    status = _check_db_status(connection)
    if status.exists and not status.expired:
        return SystemCostIndicesUpdateResult(
            update_successful=True,
            update_not_required=True,
            failure_message=None,
            previous_state=status.current_state,
            new_state=None,
        )

    return await _fetch_and_update_system_cost_indices(
        esi_link,
        schema,
        connection,
        current_state=status.current_state,
    )
