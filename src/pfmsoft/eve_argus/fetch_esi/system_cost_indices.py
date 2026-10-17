"""Fetch and update system cost indices when stored data expires."""

from functools import partial
from sqlite3 import Connection

from pfmsoft.eve_link import EsiLink, EsiResponse, EsiSchema

from pfmsoft.eve_argus.dynamic import read, write
from pfmsoft.eve_argus.dynamic.models import SystemCostIndicesResponse
from pfmsoft.eve_argus.esi import fetch as EsiFetch
from pfmsoft.eve_argus.esi import validate as EsiValidate
from pfmsoft.eve_argus.fetch_esi.update import UpdateResult, update_if_expired

type SystemCostIndicesUpdateResult = UpdateResult[SystemCostIndicesResponse]


def _current_state(connection: Connection) -> SystemCostIndicesResponse | None:
    """Return the latest stored system cost indices response, if any."""
    responses = read.system_cost_indices_responses(connection)
    return responses[0] if responses else None


def _store(connection: Connection, response: EsiResponse) -> None:
    """Validate and write a system cost indices response."""
    system_cost_indices = EsiValidate.system_cost_indices(response)
    write.system_cost_indices(connection, system_cost_indices=system_cost_indices)


async def update_system_cost_indices(
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: Connection,
) -> SystemCostIndicesUpdateResult:
    """Update system cost indices when the stored response has expired."""
    return await update_if_expired(
        read_current=partial(_current_state, connection),
        fetch=partial(EsiFetch.system_cost_indices, esi_link, schema),
        store=partial(_store, connection),
    )
