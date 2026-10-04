"""Tests for dynamic database updater modules."""

import asyncio
import sqlite3
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from pfmsoft.eve_argus.dynamic.db import load_table_definitions, query_helpers
from pfmsoft.eve_argus.dynamic.db.models import (
    CorporationBlueprintsResponse,
    CorporationIndustryJobsResponse,
    MarketsPricesResponse,
    SystemCostIndicesResponse,
)
from pfmsoft.eve_argus.dynamic.update import (
    corporation_blueprints,
    corporation_industry_jobs,
    market_orders,
    markets_prices,
)
from pfmsoft.eve_argus.dynamic.update.system_cost_indices import _current_state
from pfmsoft.eve_argus.models.esi import esi_response_models as ERM


def _make_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(load_table_definitions())
    return connection


def test_write_system_cost_indices_preserves_response_snapshots() -> None:
    """Repeated system-cost writes retain the same system in each snapshot."""
    connection = _make_connection()
    for received_at in ("2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z"):
        (
            query_helpers.write_system_cost_indices(
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

    responses = query_helpers.get_system_cost_indices_responses(connection)

    assert len(responses) == 2
    for response in responses:
        dataset = query_helpers.get_system_cost_indices(
            connection, response_metadata_id=response.response_metadata_id
        )
        assert dataset.records[30000142].response_metadata_id == (
            response.response_metadata_id
        )


def test_system_cost_indices_current_state_selects_latest_snapshot() -> None:
    """System-cost state reads the highest response metadata ID."""
    connection = _make_connection()
    for received_at in ("2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z"):
        query_helpers.write_system_cost_indices(
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing global prices response is fetched and stored."""
    connection = _make_connection()
    esi_link = object()
    schema = object()
    raw_response = object()
    prices = ERM.GetMarketsPrices(
        received_at="2026-09-01T00:00:00Z",
        expires_at="2999-01-01T00:00:00Z",
        markets_prices=[],
    )
    fetch = AsyncMock(return_value=raw_response)
    monkeypatch.setattr(markets_prices.FetchEsi, "fetch_markets_prices", fetch)
    monkeypatch.setattr(
        markets_prices.FetchEsi, "validate_markets_prices", lambda response: prices
    )

    result = asyncio.run(
        markets_prices.update_markets_prices(esi_link, schema, connection)
    )

    fetch.assert_awaited_once_with(esi_link, schema)
    assert result.update_successful is True
    assert result.update_not_required is False
    assert result.new_state == MarketsPricesResponse(
        response_metadata_id=1,
        received_at=prices.received_at,
        expires_at=prices.expires_at,
        argus_expires_at=None,
    )


def test_update_markets_prices_skips_current_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unexpired global prices response skips the ESI request."""
    connection = _make_connection()
    query_helpers.write_markets_prices(
        connection,
        ERM.GetMarketsPrices(
            received_at="2026-09-01T00:00:00Z",
            expires_at="2999-01-01T00:00:00Z",
            markets_prices=[],
        ),
    )
    fetch = AsyncMock()
    monkeypatch.setattr(markets_prices.FetchEsi, "fetch_markets_prices", fetch)

    result = asyncio.run(
        markets_prices.update_markets_prices(object(), object(), connection)
    )

    fetch.assert_not_awaited()
    assert result.update_successful is True
    assert result.update_not_required is True


def test_update_markets_prices_reports_validation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid price payloads return a failure without writing a response."""
    connection = _make_connection()
    monkeypatch.setattr(
        markets_prices.FetchEsi,
        "fetch_markets_prices",
        AsyncMock(return_value=object()),
    )

    def validate(response: object) -> ERM.GetMarketsPrices:
        raise ValueError("invalid price response")

    monkeypatch.setattr(markets_prices.FetchEsi, "validate_markets_prices", validate)

    result = asyncio.run(
        markets_prices.update_markets_prices(object(), object(), connection)
    )

    assert result.update_successful is False
    assert result.failure_message == "invalid price response"
    assert result.new_state is None
    assert query_helpers.get_markets_prices_responses(connection) == []


def test_update_market_orders_persists_new_region_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh market-order response is stored for the requested region."""
    connection = _make_connection()
    region_id = 10000002
    raw_response = object()
    orders = ERM.GetMarketsRegionIdOrders(
        received_at="2026-09-01T00:00:00Z",
        expires_at="2999-01-01T00:00:00Z",
        region_id=region_id,
        orders=[],
    )
    fetch = AsyncMock(return_value=raw_response)
    monkeypatch.setattr(market_orders.FetchEsi, "fetch_region_market_orders", fetch)
    monkeypatch.setattr(
        market_orders.FetchEsi,
        "validate_region_market_orders",
        lambda response: orders,
    )

    result = asyncio.run(
        market_orders.update_market_orders(
            object(), object(), connection, region_id=region_id
        )
    )

    fetch.assert_awaited_once()
    assert result.update_successful is True
    assert result.new_state is not None
    assert result.new_state.region_id == region_id
    assert len(query_helpers.get_market_orders_responses(connection, region_id)) == 1


def test_update_market_orders_rejects_duplicate_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An expired order response cannot be reinserted with the same timestamp."""
    connection = _make_connection()
    existing = ERM.GetMarketsRegionIdOrders(
        received_at="2026-09-01T00:00:00Z",
        expires_at="2020-01-01T00:00:00Z",
        region_id=10000002,
        orders=[],
    )
    query_helpers.write_market_orders(connection, existing)
    raw_response = object()
    fetch = AsyncMock(return_value=raw_response)
    monkeypatch.setattr(market_orders.FetchEsi, "fetch_region_market_orders", fetch)
    monkeypatch.setattr(
        market_orders.FetchEsi,
        "validate_region_market_orders",
        lambda response: existing,
    )

    result = asyncio.run(
        market_orders.update_market_orders(
            object(), object(), connection, region_id=10000002
        )
    )

    assert result.update_successful is False
    assert result.update_not_required is False
    assert "previously stored" in result.failure_message
    assert len(query_helpers.get_market_orders_responses(connection, 10000002)) == 1


def test_update_corporation_industry_jobs_passes_credentials_and_persists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Industry-job fetching passes auth context and stores the response."""
    connection = _make_connection()
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
        corporation_industry_jobs.FetchEsi,
        "fetch_corporation_industry_jobs",
        fetch,
    )
    monkeypatch.setattr(
        corporation_industry_jobs.FetchEsi,
        "validate_corporation_industry_jobs",
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
    assert result.update_successful is True
    assert result.new_state == CorporationIndustryJobsResponse(
        response_metadata_id=1,
        received_at=jobs.received_at,
        expires_at=jobs.expires_at,
        argus_expires_at=None,
        corporation_id=corporation_id,
    )


def test_update_corporation_blueprints_passes_credentials_and_persists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blueprint fetching passes auth context and stores the response."""
    connection = _make_connection()
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
        corporation_blueprints.FetchEsi,
        "fetch_corporation_blueprints",
        fetch,
    )
    monkeypatch.setattr(
        corporation_blueprints.FetchEsi,
        "validate_corporation_blueprints",
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
    assert result.update_successful is True
    assert result.new_state == CorporationBlueprintsResponse(
        response_metadata_id=1,
        received_at=blueprints.received_at,
        expires_at=blueprints.expires_at,
        argus_expires_at=None,
        corporation_id=corporation_id,
    )
