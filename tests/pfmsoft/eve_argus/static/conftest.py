"""Isolated SQLite fixtures for static database unit tests."""

from collections.abc import Iterator
from contextlib import closing
from sqlite3 import Connection, connect

import pytest

from pfmsoft.eve_argus.static.query_helpers import load_table_definitions


@pytest.fixture
def static_connection() -> Iterator[Connection]:
    """Provide an empty in-memory schema with production foreign keys enabled."""
    with closing(connect(":memory:")) as connection:
        connection.executescript(load_table_definitions())
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        yield connection
