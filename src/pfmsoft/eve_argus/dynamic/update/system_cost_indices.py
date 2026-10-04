import asyncio
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
) -> SystemCostIndicesUpdateResult: ...


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
) -> SystemCostIndicesUpdateResult: ...
