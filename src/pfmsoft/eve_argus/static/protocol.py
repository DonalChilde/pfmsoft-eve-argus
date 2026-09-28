"""Protocols for interacting with the EVE Argus static database."""

from sqlite3 import Connection
from typing import Any, Protocol

from pfmsoft.eve_argus.models.argus import static as ASM
from pfmsoft.eve_argus.models.esd import esd_datasets as ESD


class ArgusStaticDBUtilProtocol(Protocol):
    """Protocol for Argus static database utility classes.

    This covers initialization, writing datasets, and statistics gathering.
    """

    def write_blueprints(
        self, connection: Connection, *, dataset: ESD.BlueprintsDataset
    ) -> None:
        """Write the dataset of blueprints to the static database.

        Args:
            connection (Connection): The database connection to use.
            dataset (ESD.BlueprintsDataset): The dataset of blueprints to write.

        Returns:
            None
        """
        ...

    def write_industry_activities(
        self, connection: Connection, *, dataset: ESD.IndustryActivitiesDataset
    ) -> None:
        """Write the dataset of industry activities to the static database.

        Args:
            connection (Connection): The database connection to use.
            dataset (ESD.IndustryActivitiesDataset): The dataset of industry activities to write.

        Returns:
            None
        """
        ...

    def write_map_constellations(
        self, connection: Connection, *, dataset: ESD.MapConstellationsDataset
    ) -> None:
        """Write the dataset of map constellations to the static database.

        Args:
            connection (Connection): The database connection to use.
            dataset (ESD.MapConstellationsDataset): The dataset of map constellations to write.

        Returns:
            None
        """
        ...

    def write_map_regions(
        self, connection: Connection, *, dataset: ESD.MapRegionsDataset
    ) -> None:
        """Write the dataset of map regions to the static database.

        Args:
            connection (Connection): The database connection to use.
            dataset (ESD.MapRegionsDataset): The dataset of map regions to write.

        Returns:
            None
        """
        ...

    def write_map_solar_systems(
        self, connection: Connection, *, dataset: ESD.MapSolarSystemsDataset
    ) -> None:
        """Write the dataset of map solar systems to the static database.

        Args:
            connection (Connection): The database connection to use.
            dataset (ESD.MapSolarSystemsDataset): The dataset of map solar systems to write.

        Returns:
            None
        """
        ...

    def write_market_groups(
        self, connection: Connection, *, dataset: ESD.MarketGroupsDataset
    ) -> None:
        """Write the dataset of market groups to the static database.

        Args:
            connection (Connection): The database connection to use.
            dataset (ESD.MarketGroupsDataset): The dataset of market groups to write.

        Returns:
            None
        """
        ...

    def write_meta_groups(
        self, connection: Connection, *, dataset: ESD.MetaGroupsDataset
    ) -> None:
        """Write the dataset of meta groups to the static database.

        Args:
            connection (Connection): The database connection to use.
            dataset (ESD.MetaGroupsDataset): The dataset of meta groups to write.

        Returns:
            None
        """
        ...

    def write_metadata(self, connection: Connection, *, metadata: Any) -> None:
        ...
        # TODO define metadata table, and implement writing logic for it.

    def write_types(self, connection: Connection, *, dataset: ESD.TypesDataset) -> None:
        """Write the dataset of types to the static database.

        Args:
            connection (Connection): The database connection to use.
            dataset (ESD.TypesDataset): The dataset of types to write.

        Returns:
            None
        """
        ...


class ArgusStaticDBProtocol(Protocol):
    """Protocol for Argus static database classes.

    This covers query execution. Connections are managed by a separate resource manager.
    """

    def categories(
        self, connection: Connection, *, only_published: bool = True
    ) -> ASM.CategoriesDataset:
        """Retrieve the dataset of categories from the static database.

        Args:
            connection (Connection): The database connection to use.
            only_published (bool): If True, only include published categories.

        Returns:
            ASM.CategoriesDataset: The dataset of categories.
        """
        ...

    def groups(
        self, connection: Connection, *, only_published: bool = True
    ) -> ASM.GroupsDataset:
        """Retrieve the dataset of groups from the static database.

        Args:
            connection (Connection): The database connection to use.
            only_published (bool): If True, only include published groups.

        Returns:
            ASM.GroupsDataset: The dataset of groups.
        """
        ...

    def industry_activities(
        self, connection: Connection
    ) -> ASM.IndustryActivitiesDataset:
        """Retrieve the dataset of industry activities from the static database.

        Args:
            connection (Connection): The database connection to use.

        Returns:
            ASM.IndustryActivitiesDataset: The dataset of industry activities.
        """
        ...

    def map_constellations(
        self, connection: Connection
    ) -> ASM.MapConstellationsDataset:
        """Retrieve the dataset of map constellations from the static database.

        Args:
            connection (Connection): The database connection to use.

        Returns:
            ASM.MapConstellationsDataset: The dataset of map constellations.
        """
        ...

    def map_regions(self, connection: Connection) -> ASM.MapRegionsDataset:
        """Retrieve the dataset of map regions from the static database.

        Args:
            connection (Connection): The database connection to use.

        Returns:
            ASM.MapRegionsDataset: The dataset of map regions.
        """
        ...

    def map_solar_systems(self, connection: Connection) -> ASM.MapSolarSystemsDataset:
        """Retrieve the dataset of map solar systems from the static database.

        Args:
            connection (Connection): The database connection to use.

        Returns:
            ASM.MapSolarSystemsDataset: The dataset of map solar systems.
        """
        ...

    def market_groups(self, connection: Connection) -> ASM.MarketGroupsDataset:
        """Retrieve the dataset of market groups from the static database.

        Args:
            connection (Connection): The database connection to use.
            ASM.MarketGroupsDataset: The dataset of market groups.
        """
        ...

    def meta_groups(self, connection: Connection) -> ASM.MetaGroupsDataset:
        """Retrieve the dataset of meta groups from the static database.

        Args:
            connection (Connection): The database connection to use.

        Returns:
            ASM.MetaGroupsDataset: The dataset of meta groups.
        """
        ...

    def metadata(self, connection: Connection) -> Any:
        """Retrieve the metadata from the static database.

        Args:
            connection (Connection): The database connection to use.

        Returns:
            object: The metadata from the static database.
        """
        ...
        # TODO Implement metadata retrieval once the static database defines metadata storage.

    def type_materials(self, connection: Connection) -> ASM.TypeMaterialsDataset:
        """Retrieve the dataset of type materials from the static database.

        Args:
            connection (Connection): The database connection to use.

        Returns:
            ASM.TypeMaterialsDataset: The dataset of type materials.
        """
        ...

    def type_materials_randomized(
        self, connection: Connection
    ) -> ASM.TypeMaterialsRandomizedDataset:
        """Retrieve the dataset of type materials in a randomized order from the static database.

        Args:
            connection (Connection): The database connection to use.

        Returns:
            ASM.TypeMaterialsRandomizedDataset: The dataset of type materials in a randomized order.
        """
        ...

    def types(
        self, connection: Connection, *, only_published: bool = True
    ) -> ASM.TypesDataset:
        """Retrieve the dataset of types from the static database.

        Args:
            connection (Connection): The database connection to use.
            only_published (bool): If True, only include published types.

        Returns:
            ASM.TypesDataset: The dataset of types.
        """
        ...
