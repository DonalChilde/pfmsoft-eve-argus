"""Functions for writing datasets to the Argus static database."""

from sqlite3 import Connection

from pfmsoft.eve_argus.esd import models as EsdModels
from pfmsoft.eve_argus.static.db import query_helpers as QH


def blueprints(connection: Connection, *, dataset: EsdModels.BlueprintsDataset) -> None:
    """Write blueprints to the Argus static db."""
    QH.write_blueprints(connection, dataset)


def industry_activities(
    connection: Connection, *, dataset: EsdModels.IndustryActivitiesDataset
) -> None:
    """Write industry activities to the Argus static db."""
    QH.write_industry_activities(connection, dataset)


def map_constellations(
    connection: Connection, *, dataset: EsdModels.MapConstellationsDataset
) -> None:
    """Write map constellations to the Argus static db."""
    QH.write_map_constellations(connection, dataset)


def map_regions(
    connection: Connection, *, dataset: EsdModels.MapRegionsDataset
) -> None:
    """Write map regions to the Argus static db."""
    QH.write_map_regions(connection, dataset)


def map_solar_systems(
    connection: Connection, *, dataset: EsdModels.MapSolarSystemsDataset
) -> None:
    """Write map solar systems to the Argus static db."""
    QH.write_map_solar_systems(connection, dataset)


def market_groups(
    connection: Connection, *, dataset: EsdModels.MarketGroupsDataset
) -> None:
    """Write market groups to the Argus static db."""
    QH.write_market_groups(connection, dataset)


def meta_groups(
    connection: Connection, *, dataset: EsdModels.MetaGroupsDataset
) -> None:
    """Write meta groups to the Argus static db."""
    QH.write_meta_groups(connection, dataset)


def metadata(connection: Connection, *, metadata: object) -> None:
    """Reject metadata writes until the static database has metadata support."""
    raise NotImplementedError(
        "The static database does not currently define metadata storage."
    )


def types(connection: Connection, *, dataset: EsdModels.TypesDataset) -> None:
    """Write types to the Argus static db."""
    QH.write_types(connection, dataset)
