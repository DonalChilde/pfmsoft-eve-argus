"""Proof script for importing ESD data into the Argus static database."""

import sqlite3
from pathlib import Path

from pfmsoft.eve_sd import EveSdDbQueryManager

from pfmsoft.eve_argus.data_loaders.esd_datasets import EsdDatasetsLoader
from pfmsoft.eve_argus.models.types import LanguageEnum
from pfmsoft.eve_argus.static.db import query_helpers

ESD_DATABASE_PATH = Path("dev/app-dir/static-db.sqlite")
ARGUS_DATABASE_PATH = Path("dev/app-dir/argus-static-db.sqlite")


def import_static_data() -> None:
    """Import all ESD datasets into the Argus static database."""
    ARGUS_DATABASE_PATH.unlink(missing_ok=True)
    with EveSdDbQueryManager(ESD_DATABASE_PATH) as query_manager:
        loader = EsdDatasetsLoader(query_manager)
        with sqlite3.connect(ARGUS_DATABASE_PATH) as connection:
            connection.executescript(query_helpers.load_table_definitions())
            query_helpers.write_types(connection, loader.types(), LanguageEnum.EN)
            query_helpers.write_meta_groups(
                connection, loader.meta_groups(), LanguageEnum.EN
            )
            query_helpers.write_categories(
                connection, loader.categories(), LanguageEnum.EN
            )
            query_helpers.write_groups(connection, loader.groups(), LanguageEnum.EN)
            query_helpers.write_type_materials(connection, loader.type_materials())
            query_helpers.write_blueprints(connection, loader.blueprints())


if __name__ == "__main__":
    import_static_data()
