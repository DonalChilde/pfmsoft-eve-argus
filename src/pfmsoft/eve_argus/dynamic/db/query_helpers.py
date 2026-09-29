import json
import logging
import sqlite3
from dataclasses import asdict
from typing import cast

from pfmsoft.eve_argus.helpers.package_resource import load_package_resouce_text
from pfmsoft.eve_argus.helpers.timing import log_timing
from pfmsoft.eve_argus.models.argus import static as ASM
from pfmsoft.eve_argus.models.esd import esd_datasets as ESD
from pfmsoft.eve_argus.models.types import LanguageEnum

logger = logging.getLogger(__name__)

_table_def_parent = "pfmsoft.eve_argus.dynamic.db"
_table_def_file = "table_definitions.sql"
_timing_log_level = logging.INFO


def load_table_definitions() -> str:
    """Load the SQL table definitions for the market orders database."""
    return load_package_resouce_text(_table_def_parent, _table_def_file)
