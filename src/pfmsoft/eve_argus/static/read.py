"""Functions for reading datasets from the Argus static database."""

from sqlite3 import Connection
from typing import Any

from pfmsoft.eve_argus.static import models as ASM
from pfmsoft.eve_argus.static import query_helpers as QH


def categories(
    connection: Connection, *, only_published: bool = True
) -> ASM.CategoriesDataset:
    """Retrieve categories from the Argus static db."""
    return QH.get_categories(connection, only_published=only_published)


def groups(connection: Connection, *, only_published: bool = True) -> ASM.GroupsDataset:
    """Retrieve groups from the Argus static db."""
    return QH.get_groups(connection, only_published=only_published)


def industry_activities(connection: Connection) -> ASM.IndustryActivitiesDataset:
    """Retrieve industry activities from the Argus static db."""
    return QH.get_industry_activities(connection)


def map_constellations(connection: Connection) -> ASM.MapConstellationsDataset:
    """Retrieve map constellations from the Argus static db."""
    return QH.get_map_constellations(connection)


def map_regions(connection: Connection) -> ASM.MapRegionsDataset:
    """Retrieve map regions from the Argus static db."""
    return QH.get_map_regions(connection)


def map_solar_systems(connection: Connection) -> ASM.MapSolarSystemsDataset:
    """Retrieve map solar systems from the Argus static db."""
    return QH.get_map_solar_systems(connection)


def market_groups(connection: Connection) -> ASM.MarketGroupsDataset:
    """Retrieve market groups from the Argus static db."""
    return QH.get_market_groups(connection)


def meta_groups(connection: Connection) -> ASM.MetaGroupsDataset:
    """Retrieve meta groups from the Argus static db."""
    return QH.get_meta_groups(connection)


def metadata(connection: Connection) -> Any:
    """Retrieve the metadata from the Argus static db."""
    raise NotImplementedError("Metadata retrieval is not implemented yet.")


def type_materials(connection: Connection) -> ASM.TypeMaterialsDataset:
    """Retrieve type materials from the Argus static db."""
    return QH.get_type_materials(connection)


def type_materials_randomized(
    connection: Connection,
) -> ASM.TypeMaterialsRandomizedDataset:
    """Retrieve randomized type materials from the Argus static db."""
    return QH.get_type_materials_randomized(connection)


def types(connection: Connection, *, only_published: bool = True) -> ASM.TypesDataset:
    """Retrieve types from the Argus static db."""
    return QH.get_types(connection, only_published=only_published)


def sde_metadata(connection: Connection) -> ASM.SdeMetadata:
    """Retrieve SDE metadata from the Argus static db."""
    return QH.get_sde_metadata(connection)
