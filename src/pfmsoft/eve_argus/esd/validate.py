"""Validation functions for ESD datasets."""

from typing import Any

from pfmsoft.eve_sd.helpers.sde_metadata import SdeMetadata

from pfmsoft.eve_argus.esd import models as EsdModels


def blueprints(raw_dataset: dict[int, dict[str, Any]]) -> EsdModels.BlueprintsDataset:
    """Validate the raw blueprints dataset and return a BlueprintsDataset instance."""
    validated_dataset = EsdModels.BlueprintsDataset.model_validate({
        "dataset": raw_dataset
    })
    return validated_dataset


def type_materials(
    raw_dataset: dict[int, dict[str, Any]],
) -> EsdModels.TypeMaterialsDataset:
    """Validate the raw type materials dataset and return a TypeMaterialsDataset instance."""
    validated_dataset = EsdModels.TypeMaterialsDataset.model_validate({
        "dataset": raw_dataset
    })
    return validated_dataset


def types(raw_dataset: dict[int, dict[str, Any]]) -> EsdModels.TypesDataset:
    """Validate the raw types dataset and return a TypesDataset instance."""
    validated_dataset = EsdModels.TypesDataset.model_validate({"dataset": raw_dataset})
    return validated_dataset


def meta_groups(raw_dataset: dict[int, dict[str, Any]]) -> EsdModels.MetaGroupsDataset:
    """Validate the raw meta groups dataset and return a MetaGroupsDataset instance."""
    validated_dataset = EsdModels.MetaGroupsDataset.model_validate({
        "dataset": raw_dataset
    })
    return validated_dataset


def categories(raw_dataset: dict[int, dict[str, Any]]) -> EsdModels.CategoriesDataset:
    """Validate the raw categories dataset and return a CategoriesDataset instance."""
    validated_dataset = EsdModels.CategoriesDataset.model_validate({
        "dataset": raw_dataset
    })
    return validated_dataset


def groups(raw_dataset: dict[int, dict[str, Any]]) -> EsdModels.GroupsDataset:
    """Validate the raw groups dataset and return a GroupsDataset instance."""
    validated_dataset = EsdModels.GroupsDataset.model_validate({"dataset": raw_dataset})
    return validated_dataset


def industry_activities(
    raw_dataset: dict[int, dict[str, Any]],
) -> EsdModels.IndustryActivitiesDataset:
    """Validate the raw industry activities dataset and return an IndustryActivitiesDataset instance."""
    validated_dataset = EsdModels.IndustryActivitiesDataset.model_validate({
        "dataset": raw_dataset
    })
    return validated_dataset


def map_constellations(
    raw_dataset: dict[int, dict[str, Any]],
) -> EsdModels.MapConstellationsDataset:
    """Validate the raw map constellations dataset and return a MapConstellationsDataset instance."""
    validated_dataset = EsdModels.MapConstellationsDataset.model_validate({
        "dataset": raw_dataset
    })
    return validated_dataset


def map_regions(
    raw_dataset: dict[int, dict[str, Any]],
) -> EsdModels.MapRegionsDataset:
    """Validate the raw map regions dataset and return a MapRegionsDataset instance."""
    validated_dataset = EsdModels.MapRegionsDataset.model_validate({
        "dataset": raw_dataset
    })
    return validated_dataset


def map_solar_systems(
    raw_dataset: dict[int, dict[str, Any]],
) -> EsdModels.MapSolarSystemsDataset:
    """Validate the raw map solar systems dataset and return a MapSolarSystemsDataset instance."""
    validated_dataset = EsdModels.MapSolarSystemsDataset.model_validate({
        "dataset": raw_dataset
    })
    return validated_dataset


def market_groups(
    raw_dataset: dict[int, dict[str, Any]],
) -> EsdModels.MarketGroupsDataset:
    """Validate the raw market groups dataset and return a MarketGroupsDataset instance."""
    validated_dataset = EsdModels.MarketGroupsDataset.model_validate({
        "dataset": raw_dataset
    })
    return validated_dataset


def sde_metadata(
    raw_dataset: SdeMetadata,
) -> EsdModels.SdeMetadataDataset:
    """Validate the raw SDE metadata dataset and return an SdeMetadataDataset instance."""
    validated_dataset = EsdModels.SdeMetadataDataset(dataset=raw_dataset)
    return validated_dataset
