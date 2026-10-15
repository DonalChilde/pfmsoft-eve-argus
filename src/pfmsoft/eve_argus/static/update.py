from sqlite3 import Connection

from pfmsoft.eve_sd import EveSdDbQueryManager


def _is_empty(argus_connection: Connection) -> bool:
    """Check that the Argus static database is empty."""
    # check that the sde_info table does not have an entry
    # Note that the sde_info table is not yet implemented.
    return False


def create_db(argus_connection: Connection, query_manager: EveSdDbQueryManager) -> None:
    """Create the Argus static database."""
    if not _is_empty(argus_connection):
        raise RuntimeError("The Argus static database is not empty.")
