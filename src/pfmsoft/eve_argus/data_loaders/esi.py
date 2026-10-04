"""Functions to fetch and validate data from the Eve Esi API."""

from asyncio import TaskGroup
from itertools import batched
from typing import Any
from uuid import UUID

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


async def fetch_system_cost_indices(
    esi_link: EsiLink,
    schema: EsiSchema,
) -> EsiResponse | FailedEsiResponse:
    """Fetches system cost indices from ESI."""
    request = EsiRequest(
        operation_id="GetUniverseSystemCostIndices",
    )
    response = await esi_link.make_request(esi_request=request, schema=schema)
    return response


def validate_system_cost_indices(response: EsiResponse) -> ERM.GetIndustrySystems:
    """Validates system cost indices response."""
    response_dict: dict[str, Any] = {
        "received_at": _received_at_from_response(response),
        "expires_at": _expires_at_from_response(response),
        "systems": response.response_data,
    }
    return ERM.GetIndustrySystemsRoot.model_validate(response_dict).root


async def fetch_region_market_orders(
    esi_link: EsiLink, schema: EsiSchema, *, region_id: int
) -> EsiResponse | FailedEsiResponse:
    """Fetches market orders for a region."""
    request = EsiRequest(
        operation_id="GetMarketsRegionIdOrders",
        path_parameters={"region_id": region_id},
        query_parameters={"order_type": "all"},
    )
    return await esi_link.make_request(esi_request=request, schema=schema)


def validate_region_market_orders(
    response: EsiResponse,
) -> ERM.GetMarketsRegionIdOrders:
    """Validates region market orders."""
    response_dict: dict[str, Any] = {
        "received_at": _received_at_from_response(response),
        "expires_at": _expires_at_from_response(response),
        "region_id": response.esi_request.path_parameters["region_id"],
        "orders": response.response_data,
    }
    return ERM.GetMarketsRegionIdOrdersRoot.model_validate(response_dict).root


async def fetch_markets_prices(
    esi_link: EsiLink, schema: EsiSchema
) -> EsiResponse | FailedEsiResponse:
    """Fetches market prices from ESI."""
    request = EsiRequest(
        operation_id="GetMarketsPrices",
    )
    return await esi_link.make_request(esi_request=request, schema=schema)


def validate_markets_prices(response: EsiResponse) -> ERM.GetMarketsPrices:
    """Validates market prices."""
    response_dict: dict[str, Any] = {
        "received_at": _received_at_from_response(response),
        "expires_at": _expires_at_from_response(response),
        "markets_prices": response.response_data,
    }
    return ERM.GetMarketsPricesRoot.model_validate(response_dict).root


async def fetch_universe_names(
    esi_link: EsiLink, schema: EsiSchema, *, ids: set[int]
) -> list[EsiResponse | FailedEsiResponse]:
    """Fetch universe names for IDs in batches of at most 950."""
    async with TaskGroup() as task_group:
        tasks = [
            task_group.create_task(
                esi_link.make_request(
                    esi_request=EsiRequest(
                        operation_id="PostUniverseNames",
                        request_body=list(batch),
                    ),
                    schema=schema,
                )
            )
            for batch in batched(ids, 950, strict=False)
        ]
    return [task.result() for task in tasks]


def validate_universe_names(responses: list[EsiResponse]) -> ERM.PostUniverseNames:
    """Validates universe names."""
    response_dict: dict[str, Any] = {
        "received_at": _received_at_from_response(responses[0]),
        "expires_at": _expires_at_from_response(responses[0]),
        "names": [r.response_data for r in responses],
    }
    return ERM.PostUniverseNamesRoot.model_validate(response_dict).root


async def fetch_corporation_industry_jobs(
    esi_link: EsiLink,
    schema: EsiSchema,
    *,
    corporation_id: int,
    character_id: int,
    credential_id: UUID,
) -> EsiResponse | FailedEsiResponse:
    """Fetch corporation industry jobs."""
    request = EsiRequest(
        operation_id="GetCorporationsCorporationIdIndustryJobs",
        path_parameters={"corporation_id": corporation_id},
        query_parameters={"include_completed": True},
        auth_character_id=character_id,
        auth_credential_id=credential_id,
    )
    return await esi_link.make_request(esi_request=request, schema=schema)


def validate_corporation_industry_jobs(
    response: EsiResponse,
) -> ERM.GetCorporationsCorporationIdIndustryJobs:
    """Validates corporation industry jobs."""
    response_dict: dict[str, Any] = {
        "received_at": _received_at_from_response(response),
        "expires_at": _expires_at_from_response(response),
        "corporation_id": response.response_data["corporation_id"],
        "industry_jobs": response.response_data["industry_jobs"],
    }
    return ERM.GetCorporationsCorporationIdIndustryJobsRoot.model_validate(
        response_dict
    ).root


async def fetch_corporation_blueprints(
    esi_link: EsiLink,
    schema: EsiSchema,
    *,
    corporation_id: int,
    character_id: int,
    credential_id: UUID,
) -> EsiResponse | FailedEsiResponse:
    """Fetch corporation blueprints."""
    request = EsiRequest(
        operation_id="GetCorporationsCorporationIdBlueprints",
        path_parameters={"corporation_id": corporation_id},
        auth_character_id=character_id,
        auth_credential_id=credential_id,
    )
    return await esi_link.make_request(esi_request=request, schema=schema)


def validate_corporation_blueprints(
    response: EsiResponse,
) -> ERM.GetCorporationsCorporationIdBlueprints:
    """Validates corporation blueprints."""
    response_dict: dict[str, Any] = {
        "received_at": _received_at_from_response(response),
        "expires_at": _expires_at_from_response(response),
        "corporation_id": response.response_data["corporation_id"],
        "blueprints": response.response_data["blueprints"],
    }
    return ERM.GetCorporationsCorporationIdBlueprintsRoot.model_validate(
        response_dict
    ).root


async def fetch_universe_type_ids(
    esi_link: EsiLink, schema: EsiSchema
) -> EsiResponse | FailedEsiResponse:
    """Fetch universe type IDs."""
    request = EsiRequest(operation_id="GetUniverseTypes")
    return await esi_link.make_request(esi_request=request, schema=schema)


def validate_universe_type_ids(
    response: EsiResponse,
) -> ERM.GetUniverseTypes:
    """Validates universe type IDs."""
    response_dict: dict[str, Any] = {
        "received_at": _received_at_from_response(response),
        "expires_at": _expires_at_from_response(response),
        "type_ids": response.response_data["type_ids"],
    }
    return ERM.GetUniverseTypesRoot.model_validate(response_dict).root
