"""Proof script for importing ESD data into the Argus static database."""

import sqlite3
from logging import basicConfig
from pathlib import Path

from pfmsoft.eve_argus.data_loaders.esd_datasets import EsdDatasetsLoader
from pfmsoft.eve_sd import EveSdDbQueryManager

from pfmsoft.eve_argus.models.types import LanguageEnum
from pfmsoft.eve_argus.static import read, util, write

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
            connection.executescript(util.load_table_definitions())
            write.types(connection, dataset=loader.types(), language=LanguageEnum.EN)
            write.meta_groups(
                connection, dataset=loader.meta_groups(), language=LanguageEnum.EN
            )
            write.categories(
                connection, dataset=loader.categories(), language=LanguageEnum.EN
            )
            write.groups(connection, dataset=loader.groups(), language=LanguageEnum.EN)
            write.industrial_activities(
                connection, dataset=loader.industrial_activities()
            )
            write.map_regions(
                connection, dataset=loader.map_regions(), language=LanguageEnum.EN
            )
            write.map_constellations(
                connection,
                dataset=loader.map_constellations(),
                language=LanguageEnum.EN,
            )
            write.map_solar_systems(
                connection, dataset=loader.map_solar_systems(), language=LanguageEnum.EN
            )
            write.type_materials(connection, dataset=loader.type_materials())
            write.blueprints(connection, dataset=loader.blueprints())
            write.market_groups(
                connection, dataset=loader.market_groups(), language=LanguageEnum.EN
            )


def access_argus_static_data() -> None:
    """Access the Argus static database datasets."""
    with sqlite3.connect(ARGUS_DATABASE_PATH) as connection:
        market_groups = read.market_groups(connection)
        assert market_groups, "Market groups should not be empty"
        industry_activities = read.industry_activities(connection)
        assert industry_activities, "Industry activities should not be empty"
        map_regions = read.map_regions(connection)
        assert map_regions, "Map regions should not be empty"
        map_constellations = read.map_constellations(connection)
        assert map_constellations, "Map constellations should not be empty"
        map_solar_systems = read.map_solar_systems(connection)
        assert map_solar_systems, "Map solar systems should not be empty"
        groups = read.groups(connection)
        assert groups, "Groups should not be empty"
        categories = read.categories(connection)
        assert categories, "Categories should not be empty"
        type_materials = read.type_materials(connection)
        assert type_materials, "Type materials should not be empty"
        randomized_materials = read.type_materials_randomized(connection)
        assert randomized_materials, "Randomized type materials should not be empty"
        meta_groups = read.meta_groups(connection)
        assert meta_groups, "Meta groups should not be empty"
        types = read.types(connection)
        assert types, "Types should not be empty"


if __name__ == "__main__":
    setup_logging()
    import_static_data()
    access_argus_static_data()
