"""Tests for ESI response loading."""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from whenever import Instant

from pfmsoft.eve_argus.data_loaders import esi_responses
from pfmsoft.eve_argus.data_loaders.esi_responses import EsiResponseLoader

RECEIVED_AT = Instant("2025-01-01T00:00:00Z")
EXPIRES_AT = "Wed, 01 Jan 2025 01:00:00 GMT"


def run(coroutine: Any) -> Any:
    """Run one loader coroutine in the current test."""
    return asyncio.run(coroutine)


def successful_response(
    response_data: Any,
    *,
    query_parameters: dict[str, int] | None = None,
) -> SimpleNamespace:
    """Build the transport attributes consumed by the loader."""
    request = SimpleNamespace(query_parameters=query_parameters or {})
    metadata = SimpleNamespace(received_at=RECEIVED_AT, expires=EXPIRES_AT)
    return SimpleNamespace(
        response_data=response_data,
        response=SimpleNamespace(metadata=metadata),
        esi_request=request,
    )


class FakeEsiLink:
    """Async ESI link double recording requests and returning queued responses."""

    def __init__(self, responses: list[Any]) -> None:
        """Store responses and initialize request logs."""
        self.responses = iter(responses)
        self.requests: list[Any] = []
        self.schemas: list[Any] = []

    async def make_request(self, request: Any, *, schema: Any) -> Any:
        """Record a single request and return its queued response."""
        self.requests.append(request)
        self.schemas.append(schema)
        return next(self.responses)

    async def make_requests(self, request_group: Any, *, schema: Any) -> Any:
        """Record a request group and return its queued response."""
        self.requests.append(request_group)
        self.schemas.append(schema)
        return next(self.responses)


@pytest.fixture
def schema() -> object:
    """Use an opaque schema because the loader only forwards it."""
    return object()


@pytest.mark.parametrize(
    ("method_name", "operation_id", "response_data", "field_name"),
    [
        ("market_group_ids", "GetMarketsGroups", [10, 20], "market_group_ids"),
        ("markets_prices", "GetMarketsPrices", [], "markets_prices"),
        ("industry_systems", "GetIndustrySystems", [], "industry_systems"),
    ],
)
def test_simple_loaders_build_models_and_requests(
    schema: object,
    method_name: str,
    operation_id: str,
    response_data: list[Any],
    field_name: str,
) -> None:
    """Simple endpoints should forward requests and map response metadata."""
    link = FakeEsiLink([successful_response(response_data)])
    loader = EsiResponseLoader(link, schema)

    result = run(getattr(loader, method_name)())

    assert getattr(result.response_data, field_name) == response_data
    assert result.response_data.received_at == RECEIVED_AT.format_iso()
    assert (
        result.response_data.expires_at
        == Instant.parse_rfc2822(EXPIRES_AT).format_iso()
    )
    assert link.requests[0].operation_id == operation_id
    assert link.schemas == [schema]


def test_region_market_orders_maps_region_and_requests_all_orders(
    schema: object,
) -> None:
    """Regional orders should include the region and request all order types."""
    link = FakeEsiLink([
        successful_response([
            {
                "duration": 90,
                "is_buy_order": True,
                "issued": "2025-01-01T00:00:00Z",
                "location_id": 60003760,
                "min_volume": 1,
                "order_id": 1,
                "price": 10.5,
                "range": "station",
                "system_id": 30000142,
                "type_id": 34,
                "volume_remain": 5,
                "volume_total": 5,
            }
        ])
    ])
    loader = EsiResponseLoader(link, schema)

    result = run(loader.region_market_orders(10000002))

    assert result.response_data.region_id == 10000002
    assert result.response_data.orders[0].order_id == 1
    request = link.requests[0]
    assert request.operation_id == "GetMarketsRegionIdOrders"
    assert request.path_parameters == {"region_id": 10000002}
    assert request.query_parameters == {"order_type": "all"}


def test_market_groups_details_collects_each_successful_response(
    schema: object,
) -> None:
    """Market group details should retain each response under its group ID."""
    responses = SimpleNamespace(
        failed_responses={},
        successful_responses={
            "one": successful_response({
                "market_group_id": 10,
                "name": "Root",
                "description": "",
            }),
            "two": successful_response({
                "market_group_id": 20,
                "name": "Child",
                "description": "",
            }),
        },
    )
    link = FakeEsiLink([responses])
    loader = EsiResponseLoader(link, schema)

    result = run(loader.market_groups_details({10, 20}))

    assert set(result.response_data) == {10, 20}
    assert result.response_data[10].market_group.name == "Root"
    assert result.response_data[20].market_group.name == "Child"
    request_group = link.requests[0]
    assert {request.operation_id for request in request_group.requests.values()} == {
        "GetMarketsGroupsMarketGroupId"
    }
    assert {
        request.path_parameters["market_group_id"]
        for request in request_group.requests.values()
    } == {
        10,
        20,
    }


def test_region_market_histories_collects_type_ids_and_request_parameters(
    schema: object,
) -> None:
    """Regional history requests should retain the requested type IDs."""
    responses = SimpleNamespace(
        failed_responses={},
        successful_responses={
            "one": successful_response([], query_parameters={"type_id": 34}),
            "two": successful_response([], query_parameters={"type_id": 35}),
        },
    )
    link = FakeEsiLink([responses])
    loader = EsiResponseLoader(link, schema)

    result = run(loader.region_market_histories(10000002, {34, 35}))

    assert {(item.region_id, item.type_id) for item in result.response_data} == {
        (10000002, 34),
        (10000002, 35),
    }
    request_group = link.requests[0]
    assert {
        (request.path_parameters["region_id"], request.query_parameters["type_id"])
        for request in request_group.requests.values()
    } == {(10000002, 34), (10000002, 35)}


@pytest.mark.parametrize(
    "method_name",
    ["market_group_ids", "region_market_orders", "markets_prices", "industry_systems"],
)
def test_single_response_loaders_raise_for_failed_response(
    monkeypatch: pytest.MonkeyPatch,
    schema: object,
    method_name: str,
) -> None:
    """Failed single requests should expose the endpoint-specific error."""

    class FakeFailedResponse:
        def __init__(self) -> None:
            self.failed_response = SimpleNamespace(error_messages=["boom"])

    monkeypatch.setattr(esi_responses, "FailedEsiResponse", FakeFailedResponse)
    link = FakeEsiLink([FakeFailedResponse()])
    loader = EsiResponseLoader(link, schema)

    arguments = {"region_market_orders": (7,)}.get(method_name, ())
    with pytest.raises(RuntimeError, match="boom"):
        run(getattr(loader, method_name)(*arguments))


def test_grouped_loaders_raise_when_any_request_fails(
    schema: object,
) -> None:
    """Grouped endpoints should fail with the number and IDs of failed requests."""
    failed_response = SimpleNamespace(error_messages=["boom"])
    grouped_response = SimpleNamespace(
        failed_responses={
            "request-id": SimpleNamespace(failed_response=failed_response)
        },
        successful_responses={},
    )
    link = FakeEsiLink([grouped_response, grouped_response])
    loader = EsiResponseLoader(link, schema)

    with pytest.raises(RuntimeError, match="Failed to load 1 market group details"):
        run(loader.market_groups_details({10}))
    with pytest.raises(
        RuntimeError, match="Failed to load 1 market histories for region 7"
    ):
        run(loader.region_market_histories(7, {34}))
