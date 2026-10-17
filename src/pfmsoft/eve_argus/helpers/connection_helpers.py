"""Helpers for building SQLite URIs, opening connections, and bootstrapping schema."""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from sqlite3 import Connection, Row, connect

logger = logging.getLogger(__name__)


def read_only_uri(db_path: str | Path) -> str:
    """Build a read-only SQLite URI for use with sqlite3.connect(uri=True).

    Args:
        db_path: Filesystem path to the SQLite database.

    Returns:
        URI string with mode=ro.
    """
    return f"file:{db_path}?mode=ro"


def read_write_uri(db_path: str | Path) -> str:
    """Build a read-write/create SQLite URI for use with sqlite3.connect(uri=True).

    Args:
        db_path: Filesystem path to the SQLite database.

    Returns:
        URI string with mode=rwc.
    """
    return f"file:{db_path}?mode=rwc"


def init_database(
    db_path: str | Path,
    *,
    init_sql: str | None = None,
) -> None:
    """Initialize a SQLite database with the given schema if it does not already exist.

    Args:
        db_path: Path to the SQLite database file.
        init_sql: Optional SQL script to execute on the connection to ensure schema exists.


    Returns:
        Open SQLite connection configured with sqlite3.Row row factory.
    """
    logger.info(f"Initializing database at {db_path}")
    if not Path(db_path).exists():
        logger.info(f"Database at {db_path} does not exist and will be created.")
    if isinstance(db_path, Path):
        db_path = str(db_path.resolve())
    uri = read_write_uri(db_path)
    connection = connect(uri, uri=True)
    if init_sql is not None:
        with connection:
            connection.executescript(init_sql)
            logger.info(f"Executed SQL init commands for {db_path}:\n{init_sql}.")
    connection.close()


def create_read_only_connection(
    db_path: str | Path,
    *,
    row_factory: type[Row] | None = None,
) -> Connection:
    """Create a read-only SQLite connection for an existing database.

    The caller is responsible for closing the connection when done.

    Args:
        db_path: Path to an existing SQLite database file.
        row_factory: Optional row factory to use for the connection.

    Returns:
        Open SQLite connection configured with sqlite3.Row row factory.

    Notes:
        The target database is expected to already contain the required schema.
        Read-only connections cannot create temporary tables. Query helpers that
        rely on temporary tables for large key filters may fail in this mode.
    """
    if isinstance(db_path, Path):
        db_path = str(db_path.resolve())
    uri = read_only_uri(db_path)
    connection = connect(uri, uri=True)
    logger.info(f"Created read-only connection to database at {db_path}")
    if row_factory is not None:
        connection.row_factory = row_factory
        logger.info(f"Set row factory for {db_path} to {row_factory}")
    return connection


def create_read_write_connection(
    db_path: str | Path,
    *,
    init_sql: str | None = None,
    row_factory: type[Row] | None = None,
) -> Connection:
    """Create a read-write SQLite connection and optionaly ensure the packaged schema exists.

    If the database file does not exist, it will be created. If init_sql is provided,
    it will be executed to create any missing tables or other schema objects.

    The caller is responsible for closing the connection when done.

    Args:
        db_path: Path to the SQLite database file.
        init_sql: Optional SQL script to execute on the connection to ensure schema exists.
        row_factory: Optional row factory to use for the connection.

    Returns:
        Open SQLite connection configured with sqlite3.Row row factory.

    Notes:
        Missing tables and other schema objects defined in the packaged SQL
        script are created before the connection is returned.
    """
    if isinstance(db_path, Path):
        db_path = str(db_path.resolve())
    if init_sql is not None:
        init_database(db_path, init_sql=init_sql)
    uri = read_write_uri(db_path)
    connection = connect(uri, uri=True)
    logger.info(f"Created read-write connection to database at {db_path}")
    if row_factory is not None:
        connection.row_factory = row_factory
        logger.info(f"Set row factory for {db_path} to {row_factory}")
    return connection


@contextmanager
def db_connection_manager(
    db_path: str | Path,
    *,
    init_sql: str | None = None,
    read_only: bool = False,
    row_factory: type[Row] | None = None,
) -> Generator[Connection]:
    """Yield a SQLite connection and close it automatically on exit.

    Delegates to the read-only or read-write connection factory based on the
    read_only flag.

    read_only connections are expected to be used with existing databases that already
    contain the required schema. read-write connections will create the database
    file if it does not exist and will execute the init_sql script to create any missing
    tables or other schema objects.

    Args:
        db_path: Path to the SQLite database file.
        init_sql: Optional SQL script to execute on the connection to ensure schema exists.
        read_only: Whether to open the connection in read-only mode.
        row_factory: Optional row factory to use for the connection.

    Yields:
        Open SQLite connection configured with sqlite3.Row row factory.
    """
    connection: Connection | None = None
    try:
        if read_only:
            logger.info(f"Opening read-only connection to database at {db_path}")
            connection = create_read_only_connection(db_path, row_factory=row_factory)
        else:
            logger.info(f"Opening read-write connection to database at {db_path}")
            connection = create_read_write_connection(
                db_path, init_sql=init_sql, row_factory=row_factory
            )
        yield connection
    finally:
        if connection is not None:
            connection.close()
