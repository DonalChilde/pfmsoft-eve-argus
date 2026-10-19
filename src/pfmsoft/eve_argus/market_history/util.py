"""Utilities for the market history database."""

from pfmsoft.eve_argus.helpers.package_resource import load_package_resource_text

_table_def_parent = "pfmsoft.eve_argus.market_history"
_table_def_file = "table_definitions.sql"


def load_table_definitions() -> str:
    """Load the SQL table definitions for the market orders database."""
    return load_package_resource_text(_table_def_parent, _table_def_file)
