"""Test static read/write entry points and representative SQLite round trips."""

from collections.abc import Callable
from sqlite3 import Connection
from typing import Any
from unittest.mock import Mock

import pytest
from pfmsoft.eve_sd.helpers.sde_metadata import (
    SdeMetadata,
    SdeVariant,
    SourceMedia,
)

from pfmsoft.eve_argus.esd import models as ESD
from pfmsoft.eve_argus.static import models as ASM
from pfmsoft.eve_argus.static import query_helpers as QH
from pfmsoft.eve_argus.static import read, write

_READERS = (
    "categories",
    "groups",
    "industry_activities",
    "map_constellations",
    "map_regions",
    "map_solar_systems",
    "market_groups",
    "meta_groups",
    "type_materials",
    "type_materials_randomized",
    "types",
    "sde_metadata",
)
_WRITERS = (
    ("blueprints", "write_blueprints"),
    ("industrial_activities", "write_industry_activities"),
    ("map_constellations", "write_map_constellations"),
    ("map_regions", "write_map_regions"),
    ("map_solar_systems", "write_map_solar_systems"),
    ("market_groups", "write_market_groups"),
    ("meta_groups", "write_meta_groups"),
    ("types", "write_types"),
    ("type_materials", "write_type_materials"),
    ("groups", "write_groups"),
    ("categories", "write_categories"),
    ("sde_metadata", "write_sde_metadata"),
)


@pytest.mark.parametrize("name", _READERS)
def test_read_delegates(
    name: str, static_connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Forward the connection and default filter, returning the helper result."""
    result = object()
    helper = Mock(return_value=result)
    monkeypatch.setattr(QH, f"get_{name}", helper)

    assert getattr(read, name)(static_connection) is result

    kwargs = (
        {"only_published": True} if name in {"categories", "groups", "types"} else {}
    )
    helper.assert_called_once_with(static_connection, **kwargs)


@pytest.mark.parametrize("name", ["categories", "groups", "types"])
@pytest.mark.parametrize("only_published", [False, True])
def test_read_forwards_publication_filter(
    name: str,
    static_connection: Connection,
    monkeypatch: pytest.MonkeyPatch,
    *,
    only_published: bool,
) -> None:
    """Forward explicit publication filters unchanged."""
    helper = Mock()
    monkeypatch.setattr(QH, f"get_{name}", helper)

    getattr(read, name)(static_connection, only_published=only_published)

    helper.assert_called_once_with(static_connection, only_published=only_published)


@pytest.mark.parametrize(("name", "helper_name"), _WRITERS)
def test_write_delegates(
    name: str,
    helper_name: str,
    static_connection: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forward the exact dataset to its writer once without returning helper results."""
    dataset = object()
    helper = Mock()
    monkeypatch.setattr(QH, helper_name, helper)

    assert getattr(write, name)(static_connection, dataset=dataset) is None

    helper.assert_called_once_with(static_connection, dataset)


def test_metadata_placeholders_raise(static_connection: Connection) -> None:
    """Unimplemented generic metadata operations fail explicitly."""
    with pytest.raises(NotImplementedError, match="Metadata retrieval"):
        read.metadata(static_connection)
    with pytest.raises(NotImplementedError, match="metadata storage"):
        write.metadata(static_connection, metadata=object())


@pytest.mark.parametrize("name", [name for name in _READERS if name != "sde_metadata"])
def test_read_empty_dataset(name: str, static_connection: Connection) -> None:
    """An initialized database returns empty mappings, not fabricated records."""
    assert getattr(read, name)(static_connection) == {}


def test_missing_sde_metadata_raises(static_connection: Connection) -> None:
    """Missing build metadata is an error rather than an empty successful result."""
    with pytest.raises(ValueError, match="SDE metadata not found"):
        read.sde_metadata(static_connection)


@pytest.mark.parametrize("name", ["categories", "groups", "types"])
def test_publication_filter_round_trip(
    name: str, static_connection: Connection
) -> None:
    """Persist both publication states and filter only at read time."""
    if name == "categories":
        dataset = ESD.CategoriesDataset.model_validate(
            {
                "dataset": {
                    1: {"name": {"en": "Visible"}, "published": True},
                    2: {"name": {"en": "Hidden"}, "published": False},
                }
            }
        )
    elif name == "groups":
        write.categories(
            static_connection,
            dataset=ESD.CategoriesDataset.model_validate(
                {"dataset": {1: {"name": {"en": "Category"}, "published": True}}}
            ),
        )
        dataset = ESD.GroupsDataset.model_validate(
            {
                "dataset": {
                    key: {
                        "anchorable": False,
                        "anchored": False,
                        "categoryID": 1,
                        "fittableNonSingleton": True,
                        "name": {"en": label},
                        "published": published,
                        "useBasePrice": False,
                    }
                    for key, label, published in [
                        (1, "Visible", True),
                        (2, "Hidden", False),
                    ]
                }
            }
        )
    else:
        dataset = ESD.TypesDataset.model_validate(
            {
                "dataset": {
                    key: {
                        "groupID": 1,
                        "name": {"en": label},
                        "portionSize": 1,
                        "published": published,
                    }
                    for key, label, published in [
                        (1, "Visible", True),
                        (2, "Hidden", False),
                    ]
                }
            }
        )
    getattr(write, name)(static_connection, dataset=dataset)
    reader: Callable[..., dict[int, Any]] = getattr(read, name)

    published = reader(static_connection)
    all_records = reader(static_connection, only_published=False)

    assert set(published) == {1}
    assert set(all_records) == {1, 2}
    assert published[1].name == "Visible"
    assert published[1].published is True
    assert all_records[2].name == "Hidden"
    assert all_records[2].published is False


def test_materials_round_trip(static_connection: Connection) -> None:
    """Split fixed and randomized materials while retaining component quantities."""
    write.types(
        static_connection,
        dataset=ESD.TypesDataset.model_validate(
            {
                "dataset": {
                    key: {
                        "groupID": 1,
                        "name": {"en": str(key)},
                        "portionSize": 1,
                        "published": True,
                    }
                    for key in (1, 2, 3)
                }
            }
        ),
    )
    write.type_materials(
        static_connection,
        dataset=ESD.TypeMaterialsDataset.model_validate(
            {
                "dataset": {
                    1: {"materials": [{"materialTypeID": 3, "quantity": 10}]},
                    2: {
                        "randomizedMaterials": [
                            {"materialTypeID": 3, "quantityMin": 2, "quantityMax": 5}
                        ]
                    },
                    3: {},
                }
            }
        ),
    )

    assert read.type_materials(static_connection) == {
        1: ASM.TypeMaterialsRecord(
            type_id=1, materials=(ASM.Materials(material_type_id=3, quantity=10),)
        )
    }
    assert read.type_materials_randomized(static_connection) == {
        2: ASM.TypeMaterialsRandomizedRecord(
            type_id=2,
            materials=(
                ASM.RandomizedMaterials(
                    material_type_id=3, quantity_min=2, quantity_max=5
                ),
            ),
        )
    }


def test_sde_metadata_round_trip(static_connection: Connection) -> None:
    """Persist normalized build/release values without losing metadata."""
    source = SdeMetadata(
        buildNumber=3464040,
        releaseDate="2026-08-11T11:11:17Z",
        variant=SdeVariant.YAML,
        source_media=SourceMedia.DB,
    )
    write.sde_metadata(
        static_connection, dataset=ESD.SdeMetadataDataset(dataset=source)
    )

    assert read.sde_metadata(static_connection) == ASM.SdeMetadata(
        build_number=source.buildNumber, release_date=source.releaseDate
    )
