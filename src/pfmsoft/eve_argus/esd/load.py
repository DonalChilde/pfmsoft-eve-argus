"""Load data from the EVE Static Data database."""

from typing import Any

from pfmsoft.eve_sd import EveSdDbQueryManager


def blueprints(db: EveSdDbQueryManager) -> dict[int, dict[str, Any]]:
    """Load blueprints from the EVE Static Data database."""
    raw_dataset: dict[int, Any] = {
        key: value for key, value in db.query.get_int_records("blueprints")
    }
    return raw_dataset


def type_materials(db: EveSdDbQueryManager) -> dict[int, dict[str, Any]]:
    """Load type materials from the EVE Static Data database."""
    raw_dataset: dict[int, Any] = {
        key: value for key, value in db.query.get_int_records("typeMaterials")
    }
    return raw_dataset


def types(db: EveSdDbQueryManager) -> dict[int, dict[str, Any]]:
    """Load types from the EVE Static Data database."""
    raw_dataset: dict[int, Any] = {
        key: value for key, value in db.query.get_int_records("types")
    }
    return raw_dataset


def meta_groups(db: EveSdDbQueryManager) -> dict[int, dict[str, Any]]:
    """Load meta groups from the EVE Static Data database."""
    raw_dataset: dict[int, Any] = {
        key: value for key, value in db.query.get_int_records("metaGroups")
    }
    return raw_dataset


def categories(db: EveSdDbQueryManager) -> dict[int, dict[str, Any]]:
    """Load categories from the EVE Static Data database."""
    raw_dataset: dict[int, Any] = {
        key: value for key, value in db.query.get_int_records("categories")
    }
    return raw_dataset


def groups(db: EveSdDbQueryManager) -> dict[int, dict[str, Any]]:
    """Load groups from the EVE Static Data database."""
    raw_dataset: dict[int, Any] = {
        key: value for key, value in db.query.get_int_records("groups")
    }
    return raw_dataset


def industrial_activities(db: EveSdDbQueryManager) -> dict[int, dict[str, Any]]:
    """Load industrial activities from the EVE Static Data database."""
    raw_dataset: dict[int, Any] = {
        key: value for key, value in db.query.get_int_records("industrialActivities")
    }
    return raw_dataset


def map_constellations(db: EveSdDbQueryManager) -> dict[int, dict[str, Any]]:
    """Load map constellations from the EVE Static Data database."""
    raw_dataset: dict[int, Any] = {
        key: value for key, value in db.query.get_int_records("mapConstellations")
    }
    return raw_dataset


def map_regions(db: EveSdDbQueryManager) -> dict[int, dict[str, Any]]:
    """Load map regions from the EVE Static Data database."""
    raw_dataset: dict[int, Any] = {
        key: value for key, value in db.query.get_int_records("mapRegions")
    }
    return raw_dataset


def map_solar_systems(db: EveSdDbQueryManager) -> dict[int, dict[str, Any]]:
    """Load map solar systems from the EVE Static Data database."""
    raw_dataset: dict[int, Any] = {
        key: value for key, value in db.query.get_int_records("mapSolarSystems")
    }
    return raw_dataset


def market_groups(db: EveSdDbQueryManager) -> dict[int, dict[str, Any]]:
    """Load market groups from the EVE Static Data database."""
    raw_dataset: dict[int, Any] = {
        key: value for key, value in db.query.get_int_records("marketGroups")
    }
    return raw_dataset
