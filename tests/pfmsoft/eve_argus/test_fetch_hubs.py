"""Tests for the market hub fetch command."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from rich.console import Console

from pfmsoft.eve_argus.cli.market import fetch_hubs as fetch_hubs_module
from pfmsoft.eve_argus.models.market_hubs import MarketHub


class FakeResources:
    """Async resource context manager for command tests."""

    esi_link = object()
    esi_schema = object()
    order_db_connection = object()

    async def __aenter__(self) -> FakeResources:
        """Enter the fake resource context."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit the fake resource context."""
        return None


class FakeLoader:
    """Loader returning configured responses or raising configured errors."""

    def __init__(self, responses: dict[int, object | Exception]) -> None:
        """Initialize the loader with responses keyed by region ID."""
        self.responses = responses

    async def region_market_orders(self, *, region_id: int) -> object:
        """Return the configured response for a region."""
        response = self.responses[region_id]
        if isinstance(response, Exception):
            raise response
        return response


def _hub(region_id: int, system_id: int, system_name: str) -> MarketHub:
    return MarketHub(
        region_id=region_id,
        region_name=f"Region {region_id}",
        system_id=system_id,
        system_name=system_name,
        station_id=region_id,
        station_name=f"Station {region_id}",
    )


def _response(region_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        response_data=SimpleNamespace(region_id=region_id, orders=[])
    )


def test_fetch_hubs_processes_each_hub_and_scopes_summaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each hub should fetch, persist, reload, summarize, and write its report."""
    hubs = [_hub(1, 11, "Alpha"), _hub(2, 22, "Beta")]
    responses = {hub.region_id: _response(hub.region_id) for hub in hubs}
    loader = FakeLoader(responses)
    resources = FakeResources()
    report = Mock()
    report.summaries = {}
    report.iter_summaries.return_value = ["summary"]
    calculate = Mock(return_value=report)
    get_order_response = Mock(side_effect=lambda connection, region_id: region_id)
    get_region_orders = Mock(
        side_effect=lambda connection, order_response: order_response
    )
    write_orders = Mock()
    write_summaries = Mock()

    monkeypatch.setattr(fetch_hubs_module, "MARKET_HUBS", hubs)
    monkeypatch.setattr(
        fetch_hubs_module,
        "EveArgusResources",
        lambda settings: resources,
    )
    monkeypatch.setattr(
        fetch_hubs_module,
        "EsiResponseLoader",
        lambda esi_link, schema: loader,
    )
    monkeypatch.setattr(
        fetch_hubs_module.query_helpers, "write_market_orders", write_orders
    )
    monkeypatch.setattr(
        fetch_hubs_module.query_helpers,
        "get_order_response",
        get_order_response,
    )
    monkeypatch.setattr(
        fetch_hubs_module.query_helpers,
        "get_region_market_orders",
        get_region_orders,
    )
    monkeypatch.setattr(
        fetch_hubs_module.query_helpers,
        "write_order_summaries",
        write_summaries,
    )
    monkeypatch.setattr(fetch_hubs_module, "calculate_summaries", calculate)

    failures = fetch_hubs_module.asyncio.run(
        fetch_hubs_module._fetch_hubs(settings=Mock(), messenger=Console(quiet=True))
    )

    assert failures == []
    assert [call.args[1].region_id for call in write_orders.call_args_list] == [1, 2]
    assert [call.args[1] for call in get_order_response.call_args_list] == [1, 2]
    assert [call.args[1] for call in get_region_orders.call_args_list] == [1, 2]
    assert [call.kwargs["system_id"] for call in calculate.call_args_list] == [11, 22]
    assert write_summaries.call_count == 2


def test_fetch_hubs_continues_after_a_failed_hub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed hub should not prevent later hubs from being attempted."""
    hubs = [_hub(1, 11, "Alpha"), _hub(2, 22, "Beta")]
    loader = FakeLoader({1: RuntimeError("ESI unavailable"), 2: _response(2)})
    resources = FakeResources()
    report = Mock()
    report.summaries = {}
    report.iter_summaries.return_value = []

    monkeypatch.setattr(fetch_hubs_module, "MARKET_HUBS", hubs)
    monkeypatch.setattr(
        fetch_hubs_module, "EveArgusResources", lambda settings: resources
    )
    monkeypatch.setattr(
        fetch_hubs_module, "EsiResponseLoader", lambda esi_link, schema: loader
    )
    monkeypatch.setattr(
        fetch_hubs_module, "calculate_summaries", Mock(return_value=report)
    )
    monkeypatch.setattr(fetch_hubs_module.query_helpers, "write_market_orders", Mock())
    monkeypatch.setattr(
        fetch_hubs_module.query_helpers,
        "get_order_response",
        Mock(return_value=2),
    )
    monkeypatch.setattr(
        fetch_hubs_module.query_helpers,
        "get_region_market_orders",
        Mock(return_value=Mock()),
    )
    monkeypatch.setattr(
        fetch_hubs_module.query_helpers, "write_order_summaries", Mock()
    )

    failures = fetch_hubs_module.asyncio.run(
        fetch_hubs_module._fetch_hubs(settings=Mock(), messenger=Console(quiet=True))
    )

    assert failures == ["Region 1"]
    fetch_hubs_module.query_helpers.write_market_orders.assert_called_once()
