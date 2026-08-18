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
