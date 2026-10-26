"""Tests for dynamic database updater modules."""

import asyncio
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from types import ModuleType
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from pfmsoft.eve_link import EsiLink, EsiRequest, EsiResponse, EsiSchema
from whenever import Instant

from pfmsoft.eve_argus.dynamic import read, util, write
from pfmsoft.eve_argus.dynamic.models import (
    CorporationBlueprintsResponse,
    CorporationIndustryJobsResponse,
    MarketsPricesResponse,
    SystemCostIndicesResponse,
)
from pfmsoft.eve_argus.esi import models as ERM
from pfmsoft.eve_argus.fetch_esi import (
    corporation_blueprints,
    corporation_industry_jobs,
    market_orders,
    markets_prices,
    system_cost_indices,
)
from pfmsoft.eve_argus.fetch_esi.system_cost_indices import _current_state
from pfmsoft.eve_argus.fetch_esi.update import UpdateStatus


@pytest.fixture
def connection() -> Iterator[sqlite3.Connection]:
    """Provide an in-memory database with the production schema, closed afterward."""
    with closing(sqlite3.connect(":memory:")) as database:
        database.executescript(util.load_table_definitions())
        yield database


def test_write_system_cost_indices_preserves_response_snapshots(
    connection: sqlite3.Connection,
) -> None:
    """Repeated system-cost writes retain the same system in each snapshot."""
    for received_at in ("2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z"):
        (
            write.system_cost_indices(
                connection,
                ERM.GetIndustrySystems(
                    received_at=received_at,
                    expires_at="2999-01-01T00:00:00Z",
                    industry_systems=[
                        ERM.GetIndustrySystemsDetail(
                            solar_system_id=30000142,
                            cost_indices=[],
                        )
                    ],
                ),
            ),
        )

    responses = read.system_cost_indices_responses(connection)

    assert len(responses) == 2
    for response in responses:
        dataset = read.system_cost_indices(
            connection, response_metadata_id=response.response_metadata_id
        )
        assert dataset.records[30000142].response_metadata_id == (
            response.response_metadata_id
        )


def test_system_cost_indices_current_state_selects_latest_snapshot(
    connection: sqlite3.Connection,
) -> None:
    """System-cost state reads the highest response metadata ID."""
    for received_at in ("2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z"):
        write.system_cost_indices(
            connection,
            ERM.GetIndustrySystems(
                received_at=received_at,
                expires_at="2999-01-01T00:00:00Z",
                industry_systems=[],
            ),
        )

    assert _current_state(connection) == SystemCostIndicesResponse(
        response_metadata_id=2,
        received_at="2026-09-02T00:00:00Z",
        expires_at="2999-01-01T00:00:00Z",
        argus_expires_at=None,
    )


def test_update_markets_prices_persists_response(
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing global prices response is fetched and stored."""
    esi_link = object()
    schema = object()
    raw_response = object()
    prices = ERM.GetMarketsPrices(
        received_at="2026-09-01T00:00:00Z",
        expires_at="2999-01-01T00:00:00Z",
        markets_prices=[],
    )
    fetch = AsyncMock(return_value=raw_response)
    monkeypatch.setattr(markets_prices.EsiFetch, "markets_prices", fetch)
    monkeypatch.setattr(
        markets_prices.EsiValidate, "markets_prices", lambda response: prices
    )

    result = asyncio.run(
        markets_prices.update_markets_prices(esi_link, schema, connection)
    )

    fetch.assert_awaited_once_with(esi_link, schema)
    assert result.status is UpdateStatus.UPDATED
    assert result.new_state == MarketsPricesResponse(
        response_metadata_id=1,
        received_at=prices.received_at,
        expires_at=prices.expires_at,
        argus_expires_at=None,
    )


def test_update_markets_prices_skips_current_response(
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unexpired global prices response skips the ESI request."""
    write.markets_prices(
        connection,
        ERM.GetMarketsPrices(
            received_at="2026-09-01T00:00:00Z",
            expires_at="2999-01-01T00:00:00Z",
            markets_prices=[],
        ),
    )
    fetch = AsyncMock()
    monkeypatch.setattr(markets_prices.EsiFetch, "markets_prices", fetch)

    result = asyncio.run(
        markets_prices.update_markets_prices(object(), object(), connection)
    )

    fetch.assert_not_awaited()
    assert result.status is UpdateStatus.SKIPPED


def test_update_markets_prices_reports_validation_failure(
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid price payloads return a failure without writing a response."""
    monkeypatch.setattr(
        markets_prices.EsiFetch,
        "markets_prices",
        AsyncMock(return_value=object()),
    )

    def validate(response: object) -> ERM.GetMarketsPrices:
        raise ValueError("invalid price response")

    monkeypatch.setattr(markets_prices.EsiValidate, "markets_prices", validate)

    result = asyncio.run(
        markets_prices.update_markets_prices(object(), object(), connection)
    )

    assert result.status is UpdateStatus.FAILED
    assert result.failure_message == "invalid price response"
    assert result.new_state is None
    assert read.markets_prices_responses(connection) == []


def test_update_market_orders_persists_new_region_response(
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh market-order response is stored for the requested region."""
    region_id = 10000002
    raw_response = object()
    orders = ERM.GetMarketsRegionIdOrders(
        received_at="2026-09-01T00:00:00Z",
        expires_at="2999-01-01T00:00:00Z",
        region_id=region_id,
        orders=[],
    )
    fetch = AsyncMock(return_value=raw_response)
    monkeypatch.setattr(market_orders.EsiFetch, "region_market_orders", fetch)
    monkeypatch.setattr(
        market_orders.EsiValidate,
        "region_market_orders",
        lambda response: orders,
    )

    result = asyncio.run(
        market_orders.update_market_orders(
            object(), object(), connection, region_id=region_id
        )
    )

    fetch.assert_awaited_once()
    assert result.status is UpdateStatus.UPDATED
    assert result.new_state is not None
    assert result.new_state.region_id == region_id
    assert len(read.market_orders_responses(connection, region_id)) == 1


def test_update_market_orders_rejects_duplicate_timestamp(
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An expired order response cannot be reinserted with the same timestamp."""
    existing = ERM.GetMarketsRegionIdOrders(
        received_at="2026-09-01T00:00:00Z",
        expires_at="2020-01-01T00:00:00Z",
        region_id=10000002,
        orders=[],
    )
    write.market_orders(connection, existing)
    raw_response = object()
    fetch = AsyncMock(return_value=raw_response)
    monkeypatch.setattr(market_orders.EsiFetch, "region_market_orders", fetch)
    monkeypatch.setattr(
        market_orders.EsiValidate,
        "region_market_orders",
        lambda response: existing,
    )

    result = asyncio.run(
        market_orders.update_market_orders(
            object(), object(), connection, region_id=10000002
        )
    )

    assert result.status is UpdateStatus.FAILED
    assert "previously stored" in result.failure_message
    assert len(read.market_orders_responses(connection, 10000002)) == 1


def test_update_corporation_industry_jobs_passes_credentials_and_persists(
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Industry-job fetching passes auth context and stores the response."""
    esi_link = object()
    schema = object()
    corporation_id = 987654
    character_id = 123456
    credential_id = UUID("00000000-0000-0000-0000-000000000001")
    raw_response = object()
    jobs = ERM.GetCorporationsCorporationIdIndustryJobs(
        received_at="2026-09-01T00:00:00Z",
        expires_at="2999-01-01T00:00:00Z",
        corporation_id=corporation_id,
        industry_jobs=[],
    )
    fetch = AsyncMock(return_value=raw_response)
    monkeypatch.setattr(
        corporation_industry_jobs.EsiFetch,
        "corporation_industry_jobs",
        fetch,
    )
    monkeypatch.setattr(
        corporation_industry_jobs.EsiValidate,
        "corporation_industry_jobs",
        lambda response: jobs,
    )

    result = asyncio.run(
        corporation_industry_jobs.update_corporation_industry_jobs(
            esi_link,
            schema,
            connection,
            corporation_id=corporation_id,
            character_id=character_id,
            credential_id=credential_id,
        )
    )

    fetch.assert_awaited_once_with(
        esi_link,
        schema,
        corporation_id=corporation_id,
        character_id=character_id,
        credential_id=credential_id,
    )
    assert result.status is UpdateStatus.UPDATED
    assert result.new_state == CorporationIndustryJobsResponse(
        response_metadata_id=1,
        received_at=jobs.received_at,
        expires_at=jobs.expires_at,
        argus_expires_at=None,
        corporation_id=corporation_id,
    )


def test_update_corporation_blueprints_passes_credentials_and_persists(
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blueprint fetching passes auth context and stores the response."""
    esi_link = object()
    schema = object()
    corporation_id = 987654
    character_id = 123456
    credential_id = UUID("00000000-0000-0000-0000-000000000002")
    raw_response = object()
    blueprints = ERM.GetCorporationsCorporationIdBlueprints(
        received_at="2026-09-01T00:00:00Z",
        expires_at="2999-01-01T00:00:00Z",
        corporation_id=corporation_id,
        blueprints=[],
    )
    fetch = AsyncMock(return_value=raw_response)
    monkeypatch.setattr(
        corporation_blueprints.EsiFetch,
        "corporation_blueprints",
        fetch,
    )
    monkeypatch.setattr(
        corporation_blueprints.EsiValidate,
        "corporation_blueprints",
        lambda response: blueprints,
    )

    result = asyncio.run(
        corporation_blueprints.update_corporation_blueprints(
            esi_link,
            schema,
            connection,
            corporation_id=corporation_id,
            character_id=character_id,
            credential_id=credential_id,
        )
    )

    fetch.assert_awaited_once_with(
        esi_link,
        schema,
        corporation_id=corporation_id,
        character_id=character_id,
        credential_id=credential_id,
    )
    assert result.status is UpdateStatus.UPDATED
    assert result.new_state == CorporationBlueprintsResponse(
        response_metadata_id=1,
        received_at=blueprints.received_at,
        expires_at=blueprints.expires_at,
        argus_expires_at=None,
        corporation_id=corporation_id,
    )


@pytest.mark.parametrize(
    ("module", "endpoint", "operation_id", "path_parameters", "update_parameters"),
    [
        (
            markets_prices,
            "markets_prices",
            "GetMarketsPrices",
            {},
            {},
        ),
        (
            system_cost_indices,
            "system_cost_indices",
            "GetIndustrySystems",
            {},
            {},
        ),
        (
            market_orders,
            "region_market_orders",
            "GetMarketsRegionIdOrders",
            {"region_id": 10000002},
            {"region_id": 10000002},
        ),
        (
            corporation_industry_jobs,
            "corporation_industry_jobs",
            "GetCorporationsCorporationIdIndustryJobs",
            {"corporation_id": 987654},
            {
                "corporation_id": 987654,
                "character_id": 123456,
                "credential_id": UUID(int=1),
            },
        ),
        (
            corporation_blueprints,
            "corporation_blueprints",
            "GetCorporationsCorporationIdBlueprints",
            {"corporation_id": 987654},
            {
                "corporation_id": 987654,
                "character_id": 123456,
                "credential_id": UUID(int=1),
            },
        ),
    ],
)
def test_update_uses_new_esi_fetch_and_validation(
    connection: sqlite3.Connection,
    module: ModuleType,
    endpoint: str,
    operation_id: str,
    path_parameters: dict[str, int],
    update_parameters: dict[str, int | UUID],
) -> None:
    """Real fetches and validators should persist new models with only ESI mocked."""
    esi_link = Mock(spec=EsiLink)
    schema = Mock(spec=EsiSchema)
    response = Mock(spec=EsiResponse)
    response.response_data = []
    response.response.metadata.received_at = "2026-09-01T00:00:00Z"
    response.response.metadata.expires_at_instant = Instant.parse_iso(
        "2999-01-01T00:00:00Z"
    )

    async def make_request(
        *, esi_request: EsiRequest, schema: EsiSchema
    ) -> EsiResponse:
        response.esi_request = esi_request
        return response

    esi_link.make_request = AsyncMock(side_effect=make_request)
    update = getattr(module, f"update_{module.__name__.rsplit('.', 1)[-1]}")

    result = asyncio.run(update(esi_link, schema, connection, **update_parameters))

    assert module.EsiFetch.__name__ == "pfmsoft.eve_argus.esi.fetch"
    assert module.EsiValidate.__name__ == "pfmsoft.eve_argus.esi.validate"
    esi_link.make_request.assert_awaited_once()
    call = esi_link.make_request.await_args
    request = call.kwargs["esi_request"]
    assert call.kwargs["schema"] is schema
    assert request.operation_id == operation_id
    assert request.path_parameters == path_parameters
    if endpoint.startswith("corporation_"):
        assert request.auth_character_id == update_parameters["character_id"]
        assert request.auth_credential_id == update_parameters["credential_id"]
    assert result.status is UpdateStatus.UPDATED, result.failure_message
    assert result.previous_state is None
    assert result.new_state is not None
    assert result.new_state.received_at == "2026-09-01T00:00:00Z"
    assert result.new_state.expires_at == "2999-01-01T00:00:00Z"
    for key, value in path_parameters.items():
        assert getattr(result.new_state, key) == value
    assert connection.execute("SELECT COUNT(*) FROM response_metadata").fetchone() == (
        1,
    )
