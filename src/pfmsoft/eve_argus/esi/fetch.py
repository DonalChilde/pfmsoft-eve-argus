"""Fetch functions for ESI endpoints."""

from asyncio import TaskGroup
from itertools import batched
from uuid import UUID

from pfmsoft.eve_link import (
    EsiLink,
    EsiRequest,
    EsiResponse,
    EsiSchema,
    FailedEsiResponse,
)


async def market_history(
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


async def system_cost_indices(
    esi_link: EsiLink,
    schema: EsiSchema,
) -> EsiResponse | FailedEsiResponse:
    """Fetches system cost indices from ESI."""
    request = EsiRequest(
        operation_id="GetIndustrySystems",
    )
    response = await esi_link.make_request(esi_request=request, schema=schema)
    return response


async def region_market_orders(
    esi_link: EsiLink, schema: EsiSchema, *, region_id: int
) -> EsiResponse | FailedEsiResponse:
    """Fetches market orders for a region."""
    request = EsiRequest(
        operation_id="GetMarketsRegionIdOrders",
        path_parameters={"region_id": region_id},
        query_parameters={"order_type": "all"},
    )
    return await esi_link.make_request(esi_request=request, schema=schema)


async def markets_prices(
    esi_link: EsiLink, schema: EsiSchema
) -> EsiResponse | FailedEsiResponse:
    """Fetches market prices from ESI."""
    request = EsiRequest(
        operation_id="GetMarketsPrices",
    )
    return await esi_link.make_request(esi_request=request, schema=schema)


async def universe_names(
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


async def corporation_industry_jobs(
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


async def corporation_blueprints(
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


async def universe_type_ids(
    esi_link: EsiLink, schema: EsiSchema
) -> EsiResponse | FailedEsiResponse:
    """Fetch universe type IDs."""
    request = EsiRequest(operation_id="GetUniverseTypes")
    return await esi_link.make_request(esi_request=request, schema=schema)


async def market_types(
    esi_link: EsiLink, schema: EsiSchema, *, region_id: int
) -> EsiResponse | FailedEsiResponse:
    """Fetch market types for a region."""
    request = EsiRequest(
        operation_id="GetMarketsRegionIdTypes",
        path_parameters={"region_id": region_id},
    )
    return await esi_link.make_request(esi_request=request, schema=schema)
