"""Classes for accessing the Argus static db."""

from sqlite3 import Connection

from pfmsoft.eve_argus.models.argus import static as ASM
from pfmsoft.eve_argus.models.esd import esd_datasets as ESD
from pfmsoft.eve_argus.static.db import query_helpers as QH
from pfmsoft.eve_argus.static.protocol import (
    ArgusStaticDBProtocol,
    ArgusStaticDBUtilProtocol,
)


class ArgusStaticDBQuery(ArgusStaticDBProtocol):
    """Class for querying the Argus static db."""

    def categories(
        self, connection: Connection, *, only_published: bool = True
    ) -> ASM.CategoriesDataset:
        """Retrieve categories from the Argus static db."""
        return QH.get_categories(connection, only_published=only_published)

    def groups(
        self, connection: Connection, *, only_published: bool = True
    ) -> ASM.GroupsDataset:
        """Retrieve groups from the Argus static db."""
        return QH.get_groups(connection, only_published=only_published)

    def industry_activities(
        self, connection: Connection
    ) -> ASM.IndustryActivitiesDataset:
        """Retrieve industry activities from the Argus static db."""
        return QH.get_industry_activities(connection)

    def map_constellations(
        self, connection: Connection
    ) -> ASM.MapConstellationsDataset:
        """Retrieve map constellations from the Argus static db."""
        return QH.get_map_constellations(connection)

    def map_regions(self, connection: Connection) -> ASM.MapRegionsDataset:
        """Retrieve map regions from the Argus static db."""
        return QH.get_map_regions(connection)

    def map_solar_systems(self, connection: Connection) -> ASM.MapSolarSystemsDataset:
        """Retrieve map solar systems from the Argus static db."""
        return QH.get_map_solar_systems(connection)

    def market_groups(self, connection: Connection) -> ASM.MarketGroupsDataset:
        """Retrieve market groups from the Argus static db."""
        return QH.get_market_groups(connection)

    def meta_groups(self, connection: Connection) -> ASM.MetaGroupsDataset:
        """Retrieve meta groups from the Argus static db."""
        return QH.get_meta_groups(connection)

    def type_materials(self, connection: Connection) -> ASM.TypeMaterialsDataset:
        """Retrieve type materials from the Argus static db."""
        return QH.get_type_materials(connection)

    def type_materials_randomized(
        self, connection: Connection
    ) -> ASM.TypeMaterialsRandomizedDataset:
        """Retrieve randomized type materials from the Argus static db."""
        return QH.get_type_materials_randomized(connection)

    def types(
        self, connection: Connection, *, only_published: bool = True
    ) -> ASM.TypesDataset:
        """Retrieve types from the Argus static db."""
        return QH.get_types(connection, only_published=only_published)


class ArgusStaticDBUtil(ArgusStaticDBUtilProtocol):
    """Class for utility operations on the Argus static db."""

    def write_blueprints(
        self, connection: Connection, *, dataset: ESD.BlueprintsDataset
    ) -> None:
        """Write blueprints to the Argus static db."""
        QH.write_blueprints(connection, dataset)

    def write_industry_activities(
        self, connection: Connection, *, dataset: ESD.IndustryActivitiesDataset
    ) -> None:
        """Write industry activities to the Argus static db."""
        QH.write_industry_activities(connection, dataset)

    def write_map_constellations(
        self, connection: Connection, *, dataset: ESD.MapConstellationsDataset
    ) -> None:
        """Write map constellations to the Argus static db."""
        QH.write_map_constellations(connection, dataset)

    def write_map_regions(
        self, connection: Connection, *, dataset: ESD.MapRegionsDataset
    ) -> None:
        """Write map regions to the Argus static db."""
        QH.write_map_regions(connection, dataset)

    def write_map_solar_systems(
        self, connection: Connection, *, dataset: ESD.MapSolarSystemsDataset
    ) -> None:
        """Write map solar systems to the Argus static db."""
        QH.write_map_solar_systems(connection, dataset)

    def write_market_groups(
        self, connection: Connection, *, dataset: ESD.MarketGroupsDataset
    ) -> None:
        """Write market groups to the Argus static db."""
        QH.write_market_groups(connection, dataset)

    def write_meta_groups(
        self, connection: Connection, *, dataset: ESD.MetaGroupsDataset
    ) -> None:
        """Write meta groups to the Argus static db."""
        QH.write_meta_groups(connection, dataset)

    def write_metadata(self, connection: Connection, *, metadata: object) -> None:
        """Reject metadata writes until the static database has metadata support."""
        raise NotImplementedError(
            "The static database does not currently define metadata storage."
        )

    def write_types(self, connection: Connection, *, dataset: ESD.TypesDataset) -> None:
        """Write types to the Argus static db."""
        QH.write_types(connection, dataset)
