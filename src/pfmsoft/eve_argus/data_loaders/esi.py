"""Functions to fetch and validate data from the Eve Esi API."""

from typing import Any

from pfmsoft.eve_link import (
    EsiLink,
    EsiRequest,
    EsiResponse,
    EsiSchema,
    FailedEsiResponse,
)

from pfmsoft.eve_argus.models.esi import esi_response_models as ERM


def _expires_at_from_response(response: EsiResponse) -> str | None:
    """Extracts the expires_at timestamp from an ESI response."""
    expires_at = response.response.metadata.expires_at_instant
    if expires_at:
        return expires_at.format_iso()
    return None


def _received_at_from_response(response: EsiResponse) -> str:
    """Extracts the received_at timestamp from an ESI response."""
    return response.response.metadata.received_at


async def fetch_market_history(
    esi_link: EsiLink, schema: EsiSchema, *, region_id: int, type_id: int
) -> EsiResponse | FailedEsiResponse:
    """Fetches market history from ESI."""
    request = EsiRequest(
        operation_id="GetMarketsRegionIdHistory",
        path_parameters={"region_id": region_id},
        query_parameters={"type_id": type_id},
    )
    response = await esi_link.make_request(esi_request=request, schema=schema)
    return response


def validate_market_history(response: EsiResponse) -> ERM.GetMarketsRegionIdHistory:
    """Validates market history response from ESI."""
    response_dict: dict[str, Any] = {
        "received_at": _received_at_from_response(response),
        "expires_at": _expires_at_from_response(response),
        "region_id": response.esi_request.path_parameters["region_id"],
        "type_id": response.esi_request.query_parameters["type_id"],
        "history": response.response_data,
    }
    history = ERM.GetMarketsRegionIdHistoryRoot.model_validate(response_dict).root
    return history
