"""Data loader for ESI responses in the EVE Argus project."""

import asyncio
from typing import Any
from uuid import UUID

from pfmsoft.eve_link import (
    EsiLink,
    EsiRequest,
    EsiRequestGroup,
    EsiResponse,
    EsiSchema,
    FailedEsiResponse,
)
from whenever import Instant

from pfmsoft.eve_argus.data_loaders.protocols import EsiResponseLoaderProtocol
from pfmsoft.eve_argus.models.esi import esi_response


# TODO make a sensible error/exception hierarchy for ESI response loading errors, and use
# it in the loader methods.
class EsiResponseLoader(EsiResponseLoaderProtocol):
    """Loader for ESI responses."""

    def __init__(self, esi_link: EsiLink, schema: EsiSchema):
        """Initializes the loader with an ESI link interface."""
        self._esi_link = esi_link
        self._schema = schema

    async def market_group_ids(self) -> esi_response.GetMarketsGroupsResponse:
        """Loads the market group IDs from ESI."""
        request = EsiRequest(operation_id="GetMarketsGroups")
        response = await self._esi_link.make_request(request, schema=self._schema)
        if isinstance(response, FailedEsiResponse):
            raise RuntimeError(
                f"Failed to load market group IDs: {response.failed_response.error_messages}"
            )

        response_dict: dict[str, Any] = {
            "response_data": {
                "received_at": _received_at_from_response(response),
                "expires_at": _expires_at_from_response(response),
                "market_group_ids": response.response_data,
            }
        }
        return esi_response.GetMarketsGroupsResponse.model_validate(response_dict)

    async def market_groups_details(
        self, market_group_ids: set[int]
    ) -> esi_response.GetMarketsGroupsMarketGroupIdCollectedResponse:
        """Loads the market group details from ESI."""
        requests = [
            EsiRequest(
                operation_id="GetMarketsGroupsMarketGroupId",
                path_parameters={"market_group_id": group_id},
            )
            for group_id in market_group_ids
        ]
        request_group = EsiRequestGroup(requests={r.request_id: r for r in requests})
        response = await self._esi_link.make_requests(
            request_group, schema=self._schema
        )
        if response.failed_responses:
            failed_count = len(response.failed_responses)
            failed_messages = [
                f"Request ID: {request_id}, Errors: {fr.failed_response.error_messages}"
                for request_id, fr in response.failed_responses.items()
            ]
            raise RuntimeError(
                f"Failed to load {failed_count} market group details: {failed_messages}"
            )

        collected_dict: dict[str, Any] = {}
        for response_item in response.successful_responses.values():
            response_dict: dict[str, Any] = {
                "received_at": _received_at_from_response(response_item),
                "expires_at": _expires_at_from_response(response_item),
                "market_group": response_item.response_data,
            }
            market_group_id = response_item.response_data["market_group_id"]
            collected_dict[market_group_id] = response_dict

        return (
            esi_response.GetMarketsGroupsMarketGroupIdCollectedResponse.model_validate({
                "response_data": collected_dict
            })
        )

    async def region_market_orders(
        self, region_id: int
    ) -> esi_response.GetMarketsRegionIdOrdersResponse:
        """Loads the market orders for a region from ESI."""
        request = EsiRequest(
            operation_id="GetMarketsRegionIdOrders",
            path_parameters={"region_id": region_id},
            query_parameters={"order_type": "all"},
        )
        response = await self._esi_link.make_request(request, schema=self._schema)
        if isinstance(response, FailedEsiResponse):
            raise RuntimeError(
                f"Failed to load market orders for region {region_id}: {response.failed_response.error_messages}"
            )
        response_dict: dict[str, Any] = {
            "received_at": _received_at_from_response(response),
            "expires_at": _expires_at_from_response(response),
            "region_id": region_id,
            "orders": response.response_data,
        }

        return esi_response.GetMarketsRegionIdOrdersResponse.model_validate({
            "response_data": response_dict
        })

    async def region_market_histories(
        self, region_id: int, type_ids: set[int]
    ) -> esi_response.GetMarketsRegionIdHistoryCollectedResponse:
        """Loads the market history for a region and types from ESI."""
        requests = [
            EsiRequest(
                operation_id="GetMarketsRegionIdHistory",
                path_parameters={"region_id": region_id},
                query_parameters={"type_id": type_id},
            )
            for type_id in type_ids
        ]
        request_group = EsiRequestGroup(requests={r.request_id: r for r in requests})
        response = await self._esi_link.make_requests(
            request_group, schema=self._schema
        )
        if response.failed_responses:
            failed_count = len(response.failed_responses)
            failed_messages = [
                f"Request ID: {request_id}, Errors: {fr.failed_response.error_messages}"
                for request_id, fr in response.failed_responses.items()
            ]
            raise RuntimeError(
                f"Failed to load {failed_count} market histories for region {region_id}: {failed_messages}"
            )

        result_list: list[dict[str, Any]] = []
        for response_item in response.successful_responses.values():
            response_dict: dict[str, Any] = {
                "received_at": _received_at_from_response(response_item),
                "expires_at": _expires_at_from_response(response_item),
                "region_id": region_id,
                "type_id": response_item.esi_request.query_parameters["type_id"],  # type: ignore
                "history": response_item.response_data,
            }
            result_list.append(response_dict)
        return esi_response.GetMarketsRegionIdHistoryCollectedResponse.model_validate({
            "response_data": result_list
        })

    async def markets_prices(self) -> esi_response.GetMarketsPricesResponse:
        """Loads the market prices from ESI."""
        request = EsiRequest(operation_id="GetMarketsPrices")
        response = await self._esi_link.make_request(request, schema=self._schema)
        if isinstance(response, FailedEsiResponse):
            raise RuntimeError(
                f"Failed to load market prices: {response.failed_response.error_messages}"
            )
        response_dict: dict[str, Any] = {
            "received_at": _received_at_from_response(response),
            "expires_at": _expires_at_from_response(response),
            "markets_prices": response.response_data,
        }
        return esi_response.GetMarketsPricesResponse.model_validate({
            "response_data": response_dict
        })

    async def industry_systems(self) -> esi_response.GetIndustrySystemsResponse:
        """Loads the industry systems from ESI."""
        request = EsiRequest(operation_id="GetIndustrySystems")
        response = await self._esi_link.make_request(request, schema=self._schema)
        if isinstance(response, FailedEsiResponse):
            raise RuntimeError(
                f"Failed to load industry systems: {response.failed_response.error_messages}"
            )
        response_dict: dict[str, Any] = {
            "received_at": _received_at_from_response(response),
            "expires_at": _expires_at_from_response(response),
            "industry_systems": response.response_data,
        }
        return esi_response.GetIndustrySystemsResponse.model_validate({
            "response_data": response_dict
        })

    async def universe_names(
        self, ids: set[int]
    ) -> esi_response.PostUniverseNamesResponse:
        """Loads the universe names for given IDs from ESI."""
        if not ids:
            raise ValueError("The set of IDs must not be empty.")
        # The ESI endpoint for universe names requires a POST request with a JSON body
        # containing the list of IDs. The max number of IDs that can be sent in a single
        # request is 1000, so we need to batch the requests if there are more than 1000 IDs.
        # We will batch at 975 to leave some room for potential future changes in the API limit.
        batch_size = 975
        batches = [
            list(ids)[i : i + batch_size] for i in range(0, len(ids), batch_size)
        ]

        async def _load_batch(
            batch: list[int],
        ) -> esi_response.PostUniverseNamesResponse:
            """Loads a batch of universe names from ESI."""
            request = EsiRequest(
                operation_id="PostUniverseNames",
                request_body=batch,
            )
            response = await self._esi_link.make_request(request, schema=self._schema)
            if isinstance(response, FailedEsiResponse):
                raise RuntimeError(
                    f"Failed to load universe names for IDs {batch}: {response.failed_response.error_messages}"
                )
            response_dict: dict[str, Any] = {
                "received_at": _received_at_from_response(response),
                "expires_at": _expires_at_from_response(response),
                "names": response.response_data,
            }
            return esi_response.PostUniverseNamesResponse.model_validate({
                "response_data": response_dict
            })

        responses = await asyncio.gather(*[_load_batch(batch) for batch in batches])
        # Combine the results from all batches into a single response. Use the first
        # batch's received_at and expires_at for the combined response.

        combined_response_dict: dict[str, Any] = {
            "received_at": responses[0].response_data.received_at,
            "expires_at": responses[0].response_data.expires_at,
            "names": [
                name for response in responses for name in response.response_data.names
            ],
        }
        return esi_response.PostUniverseNamesResponse.model_validate({
            "response_data": combined_response_dict
        })

    async def corporation_industry_jobs(
        self,
        corporation_id: int,
        character_id: int,
        credential_id: UUID,
    ) -> esi_response.GetCorporationsCorporationIdIndustryJobsResponse:
        """Loads the industry jobs for a corporation from ESI."""
        request = EsiRequest(
            operation_id="GetCorporationsCorporationIdIndustryJobs",
            path_parameters={"corporation_id": corporation_id},
            auth_character_id=character_id,
            auth_credential_id=credential_id,
        )
        response = await self._esi_link.make_request(request, schema=self._schema)
        if isinstance(response, FailedEsiResponse):
            raise RuntimeError(
                f"Failed to load industry jobs for corporation {corporation_id}: {response.failed_response.error_messages}"
            )
        response_dict: dict[str, Any] = {
            "received_at": _received_at_from_response(response),
            "expires_at": _expires_at_from_response(response),
            "corporation_id": corporation_id,
            "industry_jobs": response.response_data,
        }
        return esi_response.GetCorporationsCorporationIdIndustryJobsResponse.model_validate({
            "response_data": response_dict
        })

    async def universe_type_ids(self) -> esi_response.GetUniverseTypesResponse:
        """Loads the universe type IDs from ESI."""
        request = EsiRequest(operation_id="GetUniverseTypes")
        response = await self._esi_link.make_request(request, schema=self._schema)
        if isinstance(response, FailedEsiResponse):
            raise RuntimeError(
                f"Failed to load universe type IDs: {response.failed_response.error_messages}"
            )
        response_dict: dict[str, Any] = {
            "received_at": _received_at_from_response(response),
            "expires_at": _expires_at_from_response(response),
            "type_ids": response.response_data,
        }
        return esi_response.GetUniverseTypesResponse.model_validate({
            "response_data": response_dict
        })


def _expires_at_from_response(response: EsiResponse) -> str | None:
    """Extracts the expires_at timestamp from an ESI response."""
    if response.response.metadata.expires:
        return Instant.parse_rfc2822(response.response.metadata.expires).format_iso()
    return None


def _received_at_from_response(response: EsiResponse) -> str:
    """Extracts the received_at timestamp from an ESI response."""
    return response.response.metadata.received_at.format_iso()
