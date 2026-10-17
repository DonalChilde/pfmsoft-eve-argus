"""Tests for all ESD load and validate functions.

Live database tests require the ``--esd-static-db PATH`` pytest CLI option.
They are skipped when that option is omitted; no default database is assumed.
Run against the current local export with:

    uv run pytest tests/pfmsoft/eve_argus/esd/test_load_validate.py \
        --esd-static-db dev/tmp/sde-db/eve_static_data_3464040_yaml.db

Mock-backed loader tests and validation unit tests run without the option.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from pfmsoft.eve_sd import EveSdDbQueryManager
from pfmsoft.eve_sd.helpers.sde_metadata import (
    SdeMetadata,
    SdeVariant,
    SourceMedia,
)
from pydantic import ValidationError

from pfmsoft.eve_argus.esd import load, models, validate

type RawDataset = dict[int, dict[str, Any]]


@dataclass(frozen=True, slots=True, kw_only=True)
class DatasetCase:
    """Loader, validator, and representative record for one integer-keyed dataset."""

    name: str
    loader: Callable[[EveSdDbQueryManager], RawDataset]
    validator: Callable[[RawDataset], models.SdeDatasetBaseModel]
    model: type[models.SdeDatasetBaseModel]
    record_type: type
    record: dict[str, Any]


_CASES = (
    DatasetCase(
        name="blueprints",
        loader=load.blueprints,
        validator=validate.blueprints,
        model=models.BlueprintsDataset,
        record_type=models.BlueprintRecord,
        record={
            "blueprintTypeID": 1,
            "activities": {"manufacturing": {"time": 60}},
        },
    ),
    DatasetCase(
        name="typeMaterials",
        loader=load.type_materials,
        validator=validate.type_materials,
        model=models.TypeMaterialsDataset,
        record_type=models.TypeMaterialsRecord,
        record={"materials": [{"materialTypeID": 34, "quantity": 100}]},
    ),
    DatasetCase(
        name="types",
        loader=load.types,
        validator=validate.types,
        model=models.TypesDataset,
        record_type=models.TypesRecord,
        record={
            "groupID": 18,
            "name": {"en": "Tritanium"},
            "portionSize": 1,
            "published": True,
        },
    ),
    DatasetCase(
        name="metaGroups",
        loader=load.meta_groups,
        validator=validate.meta_groups,
        model=models.MetaGroupsDataset,
        record_type=models.MetaGroupsRecord,
        record={"name": {"en": "Tech I"}},
    ),
    DatasetCase(
        name="categories",
        loader=load.categories,
        validator=validate.categories,
        model=models.CategoriesDataset,
        record_type=models.CategoriesRecord,
        record={"name": {"en": "Material"}, "published": True},
    ),
    DatasetCase(
        name="groups",
        loader=load.groups,
        validator=validate.groups,
        model=models.GroupsDataset,
        record_type=models.GroupsRecord,
        record={
            "anchorable": False,
            "anchored": False,
            "categoryID": 4,
            "fittableNonSingleton": False,
            "name": {"en": "Mineral"},
            "published": True,
            "useBasePrice": True,
        },
    ),
    DatasetCase(
        name="industryActivities",
        loader=load.industrial_activities,
        validator=validate.industrial_activities,
        model=models.IndustrialActivitiesDataset,
        record_type=models.IndustrialActivitiesRecord,
        record={"name": "Manufacturing", "description": "Manufacturing items"},
    ),
    DatasetCase(
        name="mapConstellations",
        loader=load.map_constellations,
        validator=validate.map_constellations,
        model=models.MapConstellationsDataset,
        record_type=models.MapConstellationsRecord,
        record={
            "name": {"en": "Kimotoro"},
            "position": {"x": 1.0, "y": 2.0, "z": 3.0},
            "regionID": 10000002,
            "solarSystemIDs": [30000142],
        },
    ),
    DatasetCase(
        name="mapRegions",
        loader=load.map_regions,
        validator=validate.map_regions,
        model=models.MapRegionsDataset,
        record_type=models.MapRegionsRecord,
        record={
            "constellationIDs": [20000020],
            "name": {"en": "The Forge"},
            "nebulaID": 1,
            "position": {"x": 1.0, "y": 2.0, "z": 3.0},
        },
    ),
    DatasetCase(
        name="mapSolarSystems",
        loader=load.map_solar_systems,
        validator=validate.map_solar_systems,
        model=models.MapSolarSystemsDataset,
        record_type=models.MapSolarSystemsRecord,
        record={
            "constellationID": 20000020,
            "name": {"en": "Jita"},
            "position": {"x": 1.0, "y": 2.0, "z": 3.0},
            "radius": 1000.0,
            "regionID": 10000002,
            "securityStatus": 0.9,
        },
    ),
    DatasetCase(
        name="marketGroups",
        loader=load.market_groups,
        validator=validate.market_groups,
        model=models.MarketGroupsDataset,
        record_type=models.MarketGroupsRecord,
        record={"hasTypes": True, "name": {"en": "Minerals"}},
    ),
)


@pytest.fixture(params=_CASES, ids=lambda case: case.name)
def case(request: pytest.FixtureRequest) -> DatasetCase:
    """Provide each supported integer-keyed dataset."""
    return request.param


@pytest.fixture
def db_mock() -> MagicMock:
    """Mock the external database manager for isolated unit tests."""
    return MagicMock(spec=EveSdDbQueryManager)


@pytest.fixture
def metadata() -> SdeMetadata:
    """Provide representative metadata without accessing a database."""
    return SdeMetadata(
        buildNumber=3464040,
        releaseDate="2026-08-11T11:11:17Z",
        variant=SdeVariant.YAML,
        source_media=SourceMedia.DB,
    )


@pytest.fixture(scope="module")
def live_db(esd_static_db_path: Path) -> Iterator[EveSdDbQueryManager]:
    """Open the explicitly supplied database and close it after the module."""
    with EveSdDbQueryManager(esd_static_db_path) as db:
        yield db


@pytest.mark.parametrize("empty", [False, True], ids=["records", "empty"])
def test_load_integer_records(
    case: DatasetCase,
    db_mock: MagicMock,
    *,
    empty: bool,
) -> None:
    """Select the correct dataset and consume its records into an integer mapping."""
    records = {} if empty else {1: case.record, 2: case.record}
    db_mock.query.get_int_records.return_value = iter(records.items())

    result = case.loader(db_mock)

    assert result == records
    assert all(type(key) is int for key in result)
    db_mock.query.get_int_records.assert_called_once_with(case.name)
    db_mock.query.get_str_records.assert_not_called()


def test_load_sde_metadata(db_mock: MagicMock, metadata: SdeMetadata) -> None:
    """Return metadata directly from the query interface."""
    db_mock.query.sde_metadata = metadata

    assert load.sde_metadata(db_mock) is metadata
    db_mock.query.get_int_records.assert_not_called()
    db_mock.query.get_str_records.assert_not_called()


@pytest.mark.parametrize("empty", [False, True], ids=["records", "empty"])
def test_validate_raw_records(case: DatasetCase, *, empty: bool) -> None:
    """Accept the raw loader output, including an empty dataset, without data loss."""
    raw = {} if empty else {1: case.record}
    expected = case.model(dataset=raw)

    result = case.validator(raw)

    assert type(result) is case.model
    assert result == expected
    assert set(result.dataset) == set(raw)
    assert all(
        isinstance(record, case.record_type) for record in result.dataset.values()
    )


def test_validate_rejects_invalid_record(case: DatasetCase) -> None:
    """Reject malformed records at the record's location inside the dataset."""
    with pytest.raises(ValidationError) as exc_info:
        case.validator({1: "invalid"})  # type: ignore[dict-item]

    assert any(
        error["loc"] == ("dataset", 1) and error["type"] == "dataclass_type"
        for error in exc_info.value.errors()
    )


def test_validate_rejects_invalid_key(case: DatasetCase) -> None:
    """Reject keys that cannot be parsed as integer record IDs."""
    with pytest.raises(ValidationError) as exc_info:
        case.validator({"invalid": case.record})  # type: ignore[dict-item]

    assert any(
        error["loc"] == ("dataset", "invalid", "[key]")
        and error["type"] == "int_parsing"
        for error in exc_info.value.errors()
    )


def test_validate_sde_metadata(metadata: SdeMetadata) -> None:
    """Wrap metadata in its typed dataset without changing its fields."""
    result = validate.sde_metadata(metadata)

    assert isinstance(result, models.SdeMetadataDataset)
    assert result.dataset == metadata


@pytest.mark.parametrize("raw", [None, "invalid", 42])
def test_validate_sde_metadata_rejects_non_metadata(raw: str | int | None) -> None:
    """Reject values that cannot represent metadata."""
    with pytest.raises(ValidationError) as exc_info:
        validate.sde_metadata(raw)  # type: ignore[arg-type]

    assert any(
        error["loc"] == ("dataset",) and error["type"] == "dataclass_type"
        for error in exc_info.value.errors()
    )


def test_live_load_records(
    case: DatasetCase,
    live_db: EveSdDbQueryManager,
) -> None:
    """Load every record, preserving the database's keys and raw field values."""
    result = case.loader(live_db)
    expected = dict(live_db.query.get_int_records(case.name))

    assert result
    assert result == expected
    assert all(type(key) is int for key in result)
    assert all(isinstance(record, dict) for record in result.values())


def test_live_validate_records(case: DatasetCase, live_db: EveSdDbQueryManager) -> None:
    """Validate the complete live dataset, not just a sample of records."""
    raw = case.loader(live_db)
    expected = case.model(dataset=raw)

    result = case.validator(raw)

    assert raw
    assert type(result) is case.model
    assert result == expected
    assert set(result.dataset) == set(raw)
    assert all(
        isinstance(record, case.record_type) for record in result.dataset.values()
    )


def test_live_sde_metadata(live_db: EveSdDbQueryManager) -> None:
    """Load and validate the live build metadata without hardcoding an export version."""
    raw = load.sde_metadata(live_db)
    result = validate.sde_metadata(raw)

    assert isinstance(raw, SdeMetadata)
    assert raw == live_db.query.sde_metadata
    assert raw.buildNumber > 0
    assert raw.releaseDate
    assert raw.source_media is SourceMedia.DB
    assert isinstance(result, models.SdeMetadataDataset)
    assert result.dataset == raw
