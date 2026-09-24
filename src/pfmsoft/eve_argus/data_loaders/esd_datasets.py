"""Data loader for ESD datasets in the EVE Argus project.

These loaders work, but the current implementation may not be the most efficient.
In the future, consider importing the required datasets into an argus format,
which can support things like localized datasets, and data subsets like published_type_id
sets.
"""

from typing import Any

from pfmsoft.eve_sd import EveSdDbQueryManager

from pfmsoft.eve_argus.data_loaders.protocols import EsdDatasetsLoaderProtocol
from pfmsoft.eve_argus.models.esd import esd_datasets


class EsdDatasetsLoader(EsdDatasetsLoaderProtocol):
    """Loader for ESD datasets."""

    def __init__(self, db_query: EveSdDbQueryManager):
        """Initializes the loader with a database query interface."""
        self.query_manager = db_query
        self._published_types_cache: set[int] | None = None

    def published_types(self) -> set[int]:
        """Returns the set of published type IDs."""
        if self._published_types_cache is None:
            self._published_types_cache = set(self.types(published=True).dataset.keys())
        return self._published_types_cache

    def blueprints(self) -> esd_datasets.BlueprintsDataset:
        """Returns the blueprints dataset loaded from ESD."""
        raw_dataset: dict[int, Any] = {
            key: value
            for key, value in self.query_manager.query.get_int_records("blueprints")
        }
        return esd_datasets.BlueprintsDataset(dataset=raw_dataset)

    def type_materials(self) -> esd_datasets.TypeMaterialsDataset:
        """Returns the type materials dataset loaded from ESD."""
        raw_dataset: dict[int, Any] = {
            key: value
            for key, value in self.query_manager.query.get_int_records("typeMaterials")
        }
        type_materials = esd_datasets.TypeMaterialsDataset(dataset=raw_dataset)
        return type_materials

    def types(self, published: bool | None = None) -> esd_datasets.TypesDataset:
        """Returns the types dataset loaded from ESD.

        Args:
            published (bool | None): If True, returns only published types. None returns
                all types. Defaults to None.
        """
        match published:
            case True:
                raw_dataset: dict[int, Any] = {
                    key: value
                    for key, value in self.query_manager.query.get_int_records("types")
                    if value.get("published") is True
                }
            case False:
                raw_dataset: dict[int, Any] = {
                    key: value
                    for key, value in self.query_manager.query.get_int_records("types")
                    if value.get("published") is False
                }
            case None:
                raw_dataset: dict[int, Any] = {
                    key: value
                    for key, value in self.query_manager.query.get_int_records("types")
                }
            case _:
                raise ValueError(
                    f"Invalid value for 'published': {published}. Must be True, False, or None."
                )
        return esd_datasets.TypesDataset(dataset=raw_dataset)

    def meta_groups(self) -> esd_datasets.MetaGroupsDataset:
        """Returns the meta groups dataset loaded from ESD."""
        raw_dataset: dict[int, Any] = {
            key: value
            for key, value in self.query_manager.query.get_int_records("metaGroups")
        }
        meta_groups = esd_datasets.MetaGroupsDataset(dataset=raw_dataset)
        return meta_groups

    def categories(self) -> esd_datasets.CategoriesDataset:
        """Returns the categories dataset loaded from ESD."""
        raw_dataset: dict[int, Any] = {
            key: value
            for key, value in self.query_manager.query.get_int_records("categories")
        }
        categories = esd_datasets.CategoriesDataset(dataset=raw_dataset)
        return categories

    def groups(self) -> esd_datasets.GroupsDataset:
        """Returns the groups dataset loaded from ESD."""
        raw_dataset: dict[int, Any] = {
            key: value
            for key, value in self.query_manager.query.get_int_records("groups")
        }
        groups = esd_datasets.GroupsDataset(dataset=raw_dataset)
        return groups

    def industrial_activities(self) -> esd_datasets.IndustryActivitiesDataset:
        """Returns the industrial activities dataset loaded from ESD."""
        raw_dataset: dict[int, Any] = {
            key: value
            for key, value in self.query_manager.query.get_int_records(
                "industryActivities"
            )
        }
        industrial_activities = esd_datasets.IndustryActivitiesDataset(
            dataset=raw_dataset
        )
        return industrial_activities

    def map_constellations(self) -> esd_datasets.MapConstellationsDataset:
        """Returns the map constellations dataset loaded from ESD."""
        raw_dataset: dict[int, Any] = {
            key: value
            for key, value in self.query_manager.query.get_int_records(
                "mapConstellations"
            )
        }
        map_constellations = esd_datasets.MapConstellationsDataset(dataset=raw_dataset)
        return map_constellations

    def map_regions(self) -> esd_datasets.MapRegionsDataset:
        """Returns the map regions dataset loaded from ESD."""
        raw_dataset: dict[int, Any] = {
            key: value
            for key, value in self.query_manager.query.get_int_records("mapRegions")
        }
        map_regions = esd_datasets.MapRegionsDataset(dataset=raw_dataset)
        return map_regions

    def map_solar_systems(self) -> esd_datasets.MapSolarSystemsDataset:
        """Returns the map solar systems dataset loaded from ESD."""
        raw_dataset: dict[int, Any] = {
            key: value
            for key, value in self.query_manager.query.get_int_records(
                "mapSolarSystems"
            )
        }
        map_solar_systems = esd_datasets.MapSolarSystemsDataset(dataset=raw_dataset)
        return map_solar_systems
