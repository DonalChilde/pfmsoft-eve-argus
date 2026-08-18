"""Data loader for ESI responses in the EVE Argus project."""

from typing import Any

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


def _expires_at_from_response(response: EsiResponse) -> str | None:
    """Extracts the expires_at timestamp from an ESI response."""
    if response.response.metadata.expires:
        return Instant.parse_rfc2822(response.response.metadata.expires).format_iso()
    return None


def _received_at_from_response(response: EsiResponse) -> str:
    """Extracts the received_at timestamp from an ESI response."""
    return response.response.metadata.received_at.format_iso()
