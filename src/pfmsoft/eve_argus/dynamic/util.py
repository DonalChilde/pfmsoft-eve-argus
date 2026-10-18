"""Utility functions for the dynamic database."""

import logging

from pfmsoft.eve_argus.helpers.package_resource import load_package_resource_text

logger = logging.getLogger(__name__)

_table_def_parent = "pfmsoft.eve_argus.dynamic"
_table_def_file = "table_definitions.sql"


def load_table_definitions() -> str:
    """Load the SQL table definitions for the dynamic database."""
    return load_package_resource_text(_table_def_parent, _table_def_file)
