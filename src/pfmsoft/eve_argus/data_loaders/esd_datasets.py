from typing import Any

from pfmsoft.eve_sd import DatasetDbQuery

from pfmsoft.eve_argus.data_loaders.protocols import EsdDatasetsLoaderProtocol
from pfmsoft.eve_argus.models.esd import esd_datasets


class EsdDatasetsLoader(EsdDatasetsLoaderProtocol):
    """Loader for ESD datasets."""

    def __init__(self, db_query: DatasetDbQuery):
        self._db_query = db_query

    def blueprints(self) -> esd_datasets.BlueprintsDataset:
        """Returns the blueprints dataset loaded from ESD."""
        raw_dataset: dict[int, Any] = {
            key: value for key, value in self._db_query.get_int_records("blueprints")
        }
        blueprints = esd_datasets.BlueprintsDatasetRoot(root=raw_dataset).root
        return blueprints
