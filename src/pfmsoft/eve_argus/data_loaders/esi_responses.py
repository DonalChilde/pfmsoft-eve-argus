"""Data loader for ESI responses in the EVE Argus project."""

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

    async def market_group_ids(self) -> esi_response.GetMarketsGroups:
        """Loads the market group IDs from ESI."""
        request = EsiRequest(operation_id="GetMarketsGroups")
        response = await self._esi_link.make_request(request, schema=self._schema)
        if isinstance(response, FailedEsiResponse):
            raise RuntimeError(
                f"Failed to load market group IDs: {response.failed_response.error_messages}"
            )
        expires_at = _expires_at_from_response(response)
        received_at = _received_at_from_response(response)
        result = esi_response.GetMarketsGroups(
            received_at=received_at,
            expires_at=expires_at,
            group_ids=response.response_data,
        )
        validated_result = esi_response.GetMarketsGroupsRoot(root=result).root
        return validated_result

    async def market_groups_details(
        self, market_group_ids: set[int]
    ) -> dict[int, esi_response.GetMarketsGroupsMarketGroupId]:
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

        result_dict: dict[int, esi_response.GetMarketsGroupsMarketGroupId] = {}
        for response_item in response.successful_responses.values():
            if isinstance(response, FailedEsiResponse):
                raise RuntimeError(
                    f"Failed to load market group details: {response.failed_response.error_messages}"
                )
            expires_at = _expires_at_from_response(response_item)
            received_at = _received_at_from_response(response_item)
            value = esi_response.GetMarketsGroupsMarketGroupId(
                received_at=received_at,
                expires_at=expires_at,
                market_group=response_item.response_data,
            )
            validated_value = esi_response.GetMarketsGroupsMarketGroupIdRoot(
                root=value
            ).root
            result_dict[validated_value.market_group.market_group_id] = validated_value
        return result_dict

    async def region_market_orders(
        self, region_id: int
    ) -> esi_response.GetMarketsRegionIdOrders:
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
        expires_at = _expires_at_from_response(response)
        received_at = _received_at_from_response(response)
        result = esi_response.GetMarketsRegionIdOrders(
            received_at=received_at,
            expires_at=expires_at,
            region_id=region_id,
            orders=response.response_data,
        )
        validated_result = esi_response.GetMarketsRegionIdOrdersRoot(root=result).root
        return validated_result

    async def region_market_histories(
        self, region_id: int, type_ids: set[int]
    ) -> dict[int, esi_response.GetMarketsRegionIdHistory]:
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

        result_dict: dict[int, esi_response.GetMarketsRegionIdHistory] = {}
        for response_item in response.successful_responses.values():
            if isinstance(response_item, FailedEsiResponse):
                raise RuntimeError(
                    f"Failed to load market history for region {region_id}: {response_item.failed_response.error_messages}"
                )
            expires_at = _expires_at_from_response(response_item)
            received_at = _received_at_from_response(response_item)
            value = esi_response.GetMarketsRegionIdHistory(
                received_at=received_at,
                expires_at=expires_at,
                region_id=region_id,
                type_id=response_item.esi_request.query_parameters["type_id"],  # type: ignore
                history=response_item.response_data,
            )
            validated_value = esi_response.GetMarketsRegionIdHistoryRoot(
                root=value
            ).root
            result_dict[validated_value.type_id] = validated_value
        return result_dict

    async def markets_prices(self) -> esi_response.GetMarketsPrices:
        """Loads the market prices from ESI."""
        request = EsiRequest(operation_id="GetMarketsPrices")
        response = await self._esi_link.make_request(request, schema=self._schema)
        if isinstance(response, FailedEsiResponse):
            raise RuntimeError(
                f"Failed to load market prices: {response.failed_response.error_messages}"
            )
        expires_at = _expires_at_from_response(response)
        received_at = _received_at_from_response(response)
        result = esi_response.GetMarketsPrices(
            received_at=received_at,
            expires_at=expires_at,
            prices=response.response_data,
        )
        validated_result = esi_response.GetMarketsPricesRoot(root=result).root
        return validated_result

    async def industry_systems(self) -> esi_response.GetIndustrySystems:
        """Loads the industry systems from ESI."""
        request = EsiRequest(operation_id="GetIndustrySystems")
        response = await self._esi_link.make_request(request, schema=self._schema)
        if isinstance(response, FailedEsiResponse):
            raise RuntimeError(
                f"Failed to load industry systems: {response.failed_response.error_messages}"
            )
        expires_at = _expires_at_from_response(response)
        received_at = _received_at_from_response(response)
        result = esi_response.GetIndustrySystems(
            received_at=received_at,
            expires_at=expires_at,
            systems=response.response_data,
        )
        validated_result = esi_response.GetIndustrySystemsRoot(root=result).root
        return validated_result


def _expires_at_from_response(response: EsiResponse) -> str | None:
    """Extracts the expires_at timestamp from an ESI response."""
    if response.response.metadata.expires:
        return Instant.parse_rfc2822(response.response.metadata.expires).format_iso()
    return None


def _received_at_from_response(response: EsiResponse) -> str:
    """Extracts the received_at timestamp from an ESI response."""
    return response.response.metadata.received_at.format_iso()
