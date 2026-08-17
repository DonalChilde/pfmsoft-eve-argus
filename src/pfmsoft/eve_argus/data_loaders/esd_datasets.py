"""Data loader for ESD datasets in the EVE Argus project."""

from typing import Any

from pfmsoft.eve_sd import EveSdDbQueryManager

from pfmsoft.eve_argus.data_loaders.protocols import EsdDatasetsLoaderProtocol
from pfmsoft.eve_argus.models.esd import esd_datasets


class EsdDatasetsLoader(EsdDatasetsLoaderProtocol):
    """Loader for ESD datasets."""

    def __init__(self, db_query: EveSdDbQueryManager):
        """Initializes the loader with a database query interface."""
        self.query_manager = db_query

    def blueprints(self) -> esd_datasets.BlueprintsDataset:
        """Returns the blueprints dataset loaded from ESD."""
        raw_dataset: dict[int, Any] = {
            key: value
            for key, value in self.query_manager.query.get_int_records("blueprints")
        }
        blueprints = esd_datasets.BlueprintsDatasetRoot(root=raw_dataset).root
        return blueprints

    def type_materials(self) -> esd_datasets.TypeMaterialsDataset:
        """Returns the type materials dataset loaded from ESD."""
        raw_dataset: dict[int, Any] = {
            key: value
            for key, value in self.query_manager.query.get_int_records("type_materials")
        }
        type_materials = esd_datasets.TypeMaterialsDatasetRoot(root=raw_dataset).root
        return type_materials

    def types(self) -> esd_datasets.TypesDataset:
        """Returns the types dataset loaded from ESD."""
        raw_dataset: dict[int, Any] = {
            key: value
            for key, value in self.query_manager.query.get_int_records("types")
        }
        types = esd_datasets.TypesDatasetRoot(root=raw_dataset).root
        return types

    def meta_groups(self) -> esd_datasets.MetaGroupsDataset:
        """Returns the meta groups dataset loaded from ESD."""
        raw_dataset: dict[int, Any] = {
            key: value
            for key, value in self.query_manager.query.get_int_records("meta_groups")
        }
        meta_groups = esd_datasets.MetaGroupsDatasetRoot(root=raw_dataset).root
        return meta_groups

    def categories(self) -> esd_datasets.CategoriesDataset:
        """Returns the categories dataset loaded from ESD."""
        raw_dataset: dict[int, Any] = {
            key: value
            for key, value in self.query_manager.query.get_int_records("categories")
        }
        categories = esd_datasets.CategoriesDatasetRoot(root=raw_dataset).root
        return categories

    def groups(self) -> esd_datasets.GroupsDataset:
        """Returns the groups dataset loaded from ESD."""
        raw_dataset: dict[int, Any] = {
            key: value
            for key, value in self.query_manager.query.get_int_records("groups")
        }
        groups = esd_datasets.GroupsDatasetRoot(root=raw_dataset).root
        return groups
