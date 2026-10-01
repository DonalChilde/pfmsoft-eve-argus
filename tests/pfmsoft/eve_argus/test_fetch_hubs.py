"""Tests for the market hub fetch command."""

import sqlite3
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from rich.console import Console
from typer.testing import CliRunner

from pfmsoft.eve_argus.cli.market import fetch_hubs as fetch_hubs_module
from pfmsoft.eve_argus.cli.market import fetch_hubs_2 as fetch_hubs_2_module
from pfmsoft.eve_argus.dynamic.db import load_table_definitions, query_helpers
from pfmsoft.eve_argus.models.esi import esi_response_models as ERM
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


def test_fetch_hubs_2_is_registered() -> None:
    """The new market command is available alongside the legacy command."""
    from pfmsoft.eve_argus.cli.market import app

    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "fetch-hubs" in result.stdout
    assert "fetch_hubs_2" in result.stdout


@pytest.mark.parametrize("failures", [[], ["Region 1"]])
def test_fetch_hubs_2_reports_failure_via_exit_code(
    monkeypatch: pytest.MonkeyPatch, failures: list[str]
) -> None:
    """The command preserves quiet mode and exits nonzero on failed hubs."""

    async def fetch(*, settings: object, messenger: Console) -> list[str]:
        assert messenger.quiet
        return failures

    monkeypatch.setattr(
        fetch_hubs_2_module, "get_eve_argus_settings_from_context", lambda ctx: Mock()
    )
    monkeypatch.setattr(fetch_hubs_2_module, "_fetch_hubs_2", fetch)

    result = CliRunner().invoke(fetch_hubs_2_module.app, ["--quiet"])

    assert result.exit_code == (1 if failures else 0)


def test_fetch_hubs_2_writes_and_summarizes_the_matching_order_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each fetched hub uses the dynamic DB and its own response metadata ID."""
    hub = _hub(1, 11, "Alpha")
    response = SimpleNamespace(
        response_data=SimpleNamespace(
            region_id=1, received_at="2026-09-01T00:00:00Z", orders=[]
        )
    )
    resources = FakeResources()
    resources.argus_dynamic_db_connection = object()
    write_orders = Mock()
    get_responses = Mock(
        side_effect=[
            [
                SimpleNamespace(
                    received_at="2026-08-01T00:00:00Z",
                    response_metadata_id=4,
                    expires_at="2026-08-02T00:00:00Z",
                    argus_expires_at=None,
                )
            ],
            [
                SimpleNamespace(
                    received_at="2026-08-01T00:00:00Z",
                    response_metadata_id=4,
                    expires_at="2026-08-02T00:00:00Z",
                    argus_expires_at=None,
                ),
                SimpleNamespace(
                    received_at="2026-09-01T00:00:00Z", response_metadata_id=7
                ),
            ],
        ]
    )
    get_orders = Mock(return_value=Mock(records={34: Mock()}))
    summary = Mock(records={34: Mock()})
    calculate = Mock(return_value=summary)
    write_summaries = Mock(return_value=3)

    monkeypatch.setattr(fetch_hubs_2_module, "MARKET_HUBS", [hub])
    monkeypatch.setattr(
        fetch_hubs_2_module, "EveArgusResources", lambda settings: resources
    )
    monkeypatch.setattr(
        fetch_hubs_2_module,
        "EsiResponseLoader",
        lambda esi_link, schema: FakeLoader({1: response}),
    )
    monkeypatch.setattr(
        fetch_hubs_2_module.query_helpers, "write_market_orders", write_orders
    )
    monkeypatch.setattr(
        fetch_hubs_2_module.query_helpers, "get_market_orders_responses", get_responses
    )
    monkeypatch.setattr(
        fetch_hubs_2_module.query_helpers, "get_market_orders", get_orders
    )
    monkeypatch.setattr(
        fetch_hubs_2_module.query_helpers, "write_order_summaries", write_summaries
    )
    monkeypatch.setattr(fetch_hubs_2_module, "calculate_summaries", calculate)

    output = StringIO()
    failures = fetch_hubs_2_module.asyncio.run(
        fetch_hubs_2_module._fetch_hubs_2(
            settings=Mock(), messenger=Console(file=output)
        )
    )

    assert failures == []
    write_orders.assert_called_once_with(
        resources.argus_dynamic_db_connection, response.response_data
    )
    assert get_responses.call_count == 2
    for call in get_responses.call_args_list:
        assert call.args == (resources.argus_dynamic_db_connection, hub.region_id)
    get_orders.assert_called_once_with(resources.argus_dynamic_db_connection, 7)
    calculate.assert_called_once_with(get_orders.return_value, system_id=hub.system_id)
    write_summaries.assert_called_once_with(
        resources.argus_dynamic_db_connection, summary
    )
    assert "Fetching market data for Alpha..." in output.getvalue()
    assert "Fetched 0 orders." in output.getvalue()
    assert "Calculated order summaries for 1 types." in output.getvalue()
    assert output.getvalue().count("Wrote order summaries to database.") == 1


def test_fetch_hubs_2_continues_after_a_failed_hub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unavailable region does not block the remaining hubs."""
    hubs = [_hub(1, 11, "Alpha"), _hub(2, 22, "Beta")]
    resources = FakeResources()
    resources.argus_dynamic_db_connection = object()
    loader = FakeLoader({1: RuntimeError("ESI unavailable"), 2: _response(2)})
    output = StringIO()
    monkeypatch.setattr(fetch_hubs_2_module, "MARKET_HUBS", hubs)
    monkeypatch.setattr(
        fetch_hubs_2_module, "EveArgusResources", lambda settings: resources
    )
    monkeypatch.setattr(
        fetch_hubs_2_module, "EsiResponseLoader", lambda esi_link, schema: loader
    )
    processed = Mock()

    async def fetch_hub(**kwargs: object) -> None:
        await loader.region_market_orders(region_id=kwargs["hub"].region_id)
        processed(kwargs["hub"])

    monkeypatch.setattr(fetch_hubs_2_module, "_fetch_hub_2", fetch_hub)

    failures = fetch_hubs_2_module.asyncio.run(
        fetch_hubs_2_module._fetch_hubs_2(
            settings=Mock(), messenger=Console(file=output)
        )
    )

    assert failures == ["Region 1"]
    processed.assert_called_once_with(hubs[1])
    assert "Failed to fetch Alpha market data: ESI unavailable" in output.getvalue()


def test_fetch_hubs_2_persists_summary_in_dynamic_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fetched response can be read back with its scoped summary."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(load_table_definitions())
    connection.row_factory = sqlite3.Row
    resources = FakeResources()
    resources.argus_dynamic_db_connection = connection
    hub = _hub(1, 11, "Alpha")
    order = ERM.GetMarketsRegionIdOrdersDetail(
        duration=90,
        is_buy_order=True,
        issued="2026-09-01T00:00:00Z",
        location_id=101,
        min_volume=1,
        order_id=201,
        price=100.0,
        range="station",
        system_id=11,
        type_id=34,
        volume_remain=10,
        volume_total=10,
    )
    response = ERM.GetMarketsRegionIdOrders(
        received_at="2026-09-01T00:00:00Z",
        expires_at=None,
        region_id=1,
        orders=[order],
    )
    monkeypatch.setattr(fetch_hubs_2_module, "MARKET_HUBS", [hub])
    monkeypatch.setattr(
        fetch_hubs_2_module, "EveArgusResources", lambda settings: resources
    )
    monkeypatch.setattr(
        fetch_hubs_2_module,
        "EsiResponseLoader",
        lambda esi_link, schema: FakeLoader({
            1: SimpleNamespace(response_data=response)
        }),
    )

    failures = fetch_hubs_2_module.asyncio.run(
        fetch_hubs_2_module._fetch_hubs_2(
            settings=Mock(), messenger=Console(quiet=True)
        )
    )

    assert failures == []
    source = query_helpers.get_market_orders_responses(connection, hub.region_id)
    assert len(source) == 1
    saved = query_helpers.get_order_summary_responses(
        connection, region_id=hub.region_id
    )
    assert len(saved) == 1
    report = query_helpers.get_order_summaries(
        connection, saved[0].order_summary_response_id
    )
    assert report.system_id == hub.system_id
    assert report.response_metadata_id == source[0].response_metadata_id
    assert report.records[34].buy_5 == 100


def test_fetch_hubs_2_can_resume_a_previous_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry can finish summaries for orders already saved at the same timestamp."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(load_table_definitions())
    connection.row_factory = sqlite3.Row
    resources = FakeResources()
    resources.argus_dynamic_db_connection = connection
    hub = _hub(1, 11, "Alpha")
    response = ERM.GetMarketsRegionIdOrders(
        received_at="2026-09-01T00:00:00Z",
        expires_at=None,
        region_id=1,
        orders=[],
    )
    monkeypatch.setattr(fetch_hubs_2_module, "MARKET_HUBS", [hub])
    monkeypatch.setattr(
        fetch_hubs_2_module, "EveArgusResources", lambda settings: resources
    )
    monkeypatch.setattr(
        fetch_hubs_2_module,
        "EsiResponseLoader",
        lambda esi_link, schema: FakeLoader({
            1: SimpleNamespace(response_data=response)
        }),
    )

    for _ in range(2):
        failures = fetch_hubs_2_module.asyncio.run(
            fetch_hubs_2_module._fetch_hubs_2(
                settings=Mock(), messenger=Console(quiet=True)
            )
        )
        assert failures == []

    assert len(query_helpers.get_market_orders_responses(connection, 1)) == 1
    assert len(query_helpers.get_order_summary_responses(connection, region_id=1)) == 1


def test_fetch_hubs_2_uses_unexpired_orders_without_network_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reuse the latest fresh order set before calling ESI, even without summaries."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(load_table_definitions())
    connection.row_factory = sqlite3.Row
    resources = FakeResources()
    resources.argus_dynamic_db_connection = connection
    hub = _hub(1, 11, "Alpha")
    query_helpers.write_market_orders(
        connection,
        ERM.GetMarketsRegionIdOrders(
            received_at="2026-09-01T00:00:00Z",
            expires_at="2999-01-01T00:00:00Z",
            region_id=hub.region_id,
            orders=[],
        ),
    )
    monkeypatch.setattr(fetch_hubs_2_module, "MARKET_HUBS", [hub])
    monkeypatch.setattr(
        fetch_hubs_2_module, "EveArgusResources", lambda settings: resources
    )
    monkeypatch.setattr(
        fetch_hubs_2_module,
        "EsiResponseLoader",
        lambda esi_link, schema: FakeLoader({
            hub.region_id: RuntimeError("unexpected ESI request")
        }),
    )

    output = StringIO()
    failures = fetch_hubs_2_module.asyncio.run(
        fetch_hubs_2_module._fetch_hubs_2(
            settings=Mock(), messenger=Console(file=output)
        )
    )

    assert failures == []
    assert "Orders already in database." in output.getvalue()
    assert (
        len(query_helpers.get_market_orders_responses(connection, hub.region_id)) == 1
    )
    assert len(query_helpers.get_order_summary_responses(connection, region_id=1)) == 1


@pytest.mark.parametrize(
    ("expires_at", "argus_expires_at"),
    [
        ("2020-01-01T00:00:00Z", None),
        ("2999-01-01T00:00:00Z", "2020-01-01T00:00:00Z"),
        (None, None),
    ],
)
def test_fetch_hubs_2_refreshes_expired_orders(
    monkeypatch: pytest.MonkeyPatch,
    expires_at: str | None,
    argus_expires_at: str | None,
) -> None:
    """Expired or undated orders trigger a new fetch and response timestamp."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(load_table_definitions())
    connection.row_factory = sqlite3.Row
    resources = FakeResources()
    resources.argus_dynamic_db_connection = connection
    hub = _hub(1, 11, "Alpha")
    query_helpers.write_market_orders(
        connection,
        ERM.GetMarketsRegionIdOrders(
            received_at="2026-09-01T00:00:00Z",
            expires_at=expires_at,
            region_id=hub.region_id,
            orders=[],
        ),
    )
    connection.execute(
        "UPDATE response_metadata SET argus_expires_at = ? WHERE id = 1",
        (argus_expires_at,),
    )
    connection.commit()
    fetched = ERM.GetMarketsRegionIdOrders(
        received_at="2026-10-01T00:00:00Z",
        expires_at="2999-01-01T00:00:00Z",
        region_id=hub.region_id,
        orders=[],
    )
    monkeypatch.setattr(fetch_hubs_2_module, "MARKET_HUBS", [hub])
    monkeypatch.setattr(
        fetch_hubs_2_module, "EveArgusResources", lambda settings: resources
    )
    monkeypatch.setattr(
        fetch_hubs_2_module,
        "EsiResponseLoader",
        lambda esi_link, schema: FakeLoader({
            hub.region_id: SimpleNamespace(response_data=fetched)
        }),
    )

    failures = fetch_hubs_2_module.asyncio.run(
        fetch_hubs_2_module._fetch_hubs_2(
            settings=Mock(), messenger=Console(quiet=True)
        )
    )

    assert failures == []
    responses = query_helpers.get_market_orders_responses(connection, hub.region_id)
    assert [item.received_at for item in responses] == [
        "2026-09-01T00:00:00Z",
        "2026-10-01T00:00:00Z",
    ]
    summaries = query_helpers.get_order_summary_responses(
        connection, region_id=hub.region_id
    )
    assert len(summaries) == 1


def test_fetch_hubs_2_rejects_expired_response_without_new_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An expired order set cannot be passed off as newly fetched data."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(load_table_definitions())
    connection.row_factory = sqlite3.Row
    resources = FakeResources()
    resources.argus_dynamic_db_connection = connection
    hub = _hub(1, 11, "Alpha")
    response = ERM.GetMarketsRegionIdOrders(
        received_at="2026-09-01T00:00:00Z",
        expires_at="2020-01-01T00:00:00Z",
        region_id=hub.region_id,
        orders=[],
    )
    query_helpers.write_market_orders(connection, response)
    monkeypatch.setattr(fetch_hubs_2_module, "MARKET_HUBS", [hub])
    monkeypatch.setattr(
        fetch_hubs_2_module, "EveArgusResources", lambda settings: resources
    )
    monkeypatch.setattr(
        fetch_hubs_2_module,
        "EsiResponseLoader",
        lambda esi_link, schema: FakeLoader({
            hub.region_id: SimpleNamespace(response_data=response)
        }),
    )

    output = StringIO()
    failures = fetch_hubs_2_module.asyncio.run(
        fetch_hubs_2_module._fetch_hubs_2(
            settings=Mock(), messenger=Console(file=output)
        )
    )

    assert failures == [hub.region_name]
    assert "expired" in output.getvalue()
    assert (
        len(query_helpers.get_market_orders_responses(connection, hub.region_id)) == 1
    )
    assert query_helpers.get_order_summary_responses(connection, region_id=1) == []
