"""Create the Argus static database."""

from sqlite3 import Connection

from pfmsoft.eve_sd import EveSdDbQueryManager

from pfmsoft.eve_argus.esd import load as EsdLoad
from pfmsoft.eve_argus.esd import validate as EsdValidate
from pfmsoft.eve_argus.static import read, write


def _is_empty(argus_connection: Connection) -> bool:
    """Check that the Argus static database is empty."""
    try:
        foo = read.sde_metadata(argus_connection)
        if foo:
            return False
    except Exception:
        return True
    return True


def create_db(argus_connection: Connection, query_manager: EveSdDbQueryManager) -> None:
    """Create the Argus static database.

    The connection must be to an empty but configured Argus static database.
    """
    if not _is_empty(argus_connection):
        raise RuntimeError("The Argus static database is not empty.")
    blueprints = EsdValidate.blueprints(EsdLoad.blueprints(query_manager))
    write.blueprints(argus_connection, dataset=blueprints)
    type_materials = EsdValidate.type_materials(EsdLoad.type_materials(query_manager))
    write.type_materials(argus_connection, dataset=type_materials)
    types = EsdValidate.types(EsdLoad.types(query_manager))
    write.types(argus_connection, dataset=types)
    meta_groups = EsdValidate.meta_groups(EsdLoad.meta_groups(query_manager))
    write.meta_groups(argus_connection, dataset=meta_groups)
    categories = EsdValidate.categories(EsdLoad.categories(query_manager))
    write.categories(argus_connection, dataset=categories)
    groups = EsdValidate.groups(EsdLoad.groups(query_manager))
    write.groups(argus_connection, dataset=groups)
    industrial_activities = EsdValidate.industrial_activities(
        EsdLoad.industrial_activities(query_manager)
    )
    write.industrial_activities(argus_connection, dataset=industrial_activities)
    map_constellations = EsdValidate.map_constellations(
        EsdLoad.map_constellations(query_manager)
    )
    write.map_constellations(argus_connection, dataset=map_constellations)
    map_regions = EsdValidate.map_regions(EsdLoad.map_regions(query_manager))
    write.map_regions(argus_connection, dataset=map_regions)
    map_solar_systems = EsdValidate.map_solar_systems(
        EsdLoad.map_solar_systems(query_manager)
    )
    write.map_solar_systems(argus_connection, dataset=map_solar_systems)
    market_groups = EsdValidate.market_groups(EsdLoad.market_groups(query_manager))
    write.market_groups(argus_connection, dataset=market_groups)
    sde_metadata = EsdValidate.sde_metadata(EsdLoad.sde_metadata(query_manager))
    write.sde_metadata(argus_connection, dataset=sde_metadata)
