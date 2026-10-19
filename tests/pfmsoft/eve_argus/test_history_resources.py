"""Regression tests for market-history resource initialization."""

import asyncio
import sqlite3
from unittest.mock import AsyncMock, Mock

import pytest


def test_resources_initialize_history_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resource startup loads the active history schema without network access."""
    from pfmsoft.eve_argus import eve_argus

    settings = Mock()
    simple_requests = Mock()
    esi_link = Mock()
    esi_link.__aenter__ = AsyncMock()
    esi_link.__aexit__ = AsyncMock()
    simple_requests.esi_link_factory.return_value = esi_link
    monkeypatch.setattr(eve_argus, "SimpleRequests", Mock(return_value=simple_requests))
    monkeypatch.setattr(eve_argus, "StaticStore", Mock())

    def create_connection(
        path: object, *, init_sql: str | None = None
    ) -> sqlite3.Connection:
        connection = sqlite3.connect(":memory:")
        if init_sql is not None:
            connection.executescript(init_sql)
        return connection

    monkeypatch.setattr(eve_argus, "create_read_write_connection", create_connection)

    async def check_resources() -> None:
        async with eve_argus.EveArgusResources(settings) as resources:
            connection = resources.market_history_db_connection
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            assert {"market_history", "market_history_response"} <= tables
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")

    asyncio.run(check_resources())
    esi_link.__aenter__.assert_awaited_once()
    esi_link.__aexit__.assert_awaited_once()
