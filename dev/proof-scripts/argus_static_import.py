"""Proof script for importing ESD data into the Argus static database."""

import sqlite3
from logging import basicConfig
from pathlib import Path

from pfmsoft.eve_sd import EveSdDbQueryManager

from pfmsoft.eve_argus.data_loaders.esd_datasets import EsdDatasetsLoader
from pfmsoft.eve_argus.models.types import LanguageEnum
from pfmsoft.eve_argus.static.db import query_helpers

ESD_DATABASE_PATH = Path("dev/app-dir/static-db.sqlite")
ARGUS_DATABASE_PATH = Path("dev/app-dir/argus-static-db.sqlite")
LOG_FILE_PATH = Path("dev/proof-scripts/logging/argus_static_import.log")


def setup_logging() -> None:
    """Configure logging for the static data import proof script."""
    LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    basicConfig(
        filename=LOG_FILE_PATH,
        level="INFO",
        format="%(asctime)s | %(levelname)-8s | %(funcName)s | %(message)s | [in %(pathname)s | %(lineno)d]",
    )


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
            query_helpers.write_industry_activities(
                connection, loader.industrial_activities()
            )
            query_helpers.write_map_regions(
                connection, loader.map_regions(), LanguageEnum.EN
            )
            query_helpers.write_map_constellations(
                connection, loader.map_constellations(), LanguageEnum.EN
            )
            query_helpers.write_map_solar_systems(
                connection, loader.map_solar_systems(), LanguageEnum.EN
            )
            query_helpers.write_type_materials(connection, loader.type_materials())
            query_helpers.write_blueprints(connection, loader.blueprints())
            query_helpers.write_market_groups(
                connection, loader.market_groups(), LanguageEnum.EN
            )


def access_argus_static_data() -> None:
    """Access the Argus static database datasets."""
    with sqlite3.connect(ARGUS_DATABASE_PATH) as connection:
        market_groups = query_helpers.get_market_groups(connection)
        assert market_groups, "Market groups should not be empty"
        industry_activities = query_helpers.get_industry_activities(connection)
        assert industry_activities, "Industry activities should not be empty"
        map_regions = query_helpers.get_map_regions(connection)
        assert map_regions, "Map regions should not be empty"
        map_constellations = query_helpers.get_map_constellations(connection)
        assert map_constellations, "Map constellations should not be empty"
        map_solar_systems = query_helpers.get_map_solar_systems(connection)
        assert map_solar_systems, "Map solar systems should not be empty"
        groups = query_helpers.get_groups(connection)
        assert groups, "Groups should not be empty"
        categories = query_helpers.get_categories(connection)
        assert categories, "Categories should not be empty"
        type_materials = query_helpers.get_type_materials(connection)
        assert type_materials, "Type materials should not be empty"
        randomized_materials = query_helpers.get_type_materials_randomized(connection)
        assert randomized_materials, "Randomized type materials should not be empty"
        meta_groups = query_helpers.get_meta_groups(connection)
        assert meta_groups, "Meta groups should not be empty"
        types = query_helpers.get_types(connection)
        assert types, "Types should not be empty"


if __name__ == "__main__":
    setup_logging()
    import_static_data()
    access_argus_static_data()
