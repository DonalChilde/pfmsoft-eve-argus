"""Tests for ESD dataset loading."""

from types import SimpleNamespace

import pytest

from pfmsoft.eve_argus.data_loaders.esd_datasets import EsdDatasetsLoader


class FakeQuery:
    """Minimal query interface used by the ESD loader."""

    def __init__(self, records: dict[str, list[tuple[int, dict]]]) -> None:
        """Store records and initialize the call log."""
        self.records = records
        self.calls: list[str] = []

    def get_int_records(self, dataset_name: str) -> list[tuple[int, dict]]:
        """Return records for one dataset and record the lookup."""
        self.calls.append(dataset_name)
        return self.records[dataset_name]


@pytest.fixture
def loader_and_query() -> tuple[EsdDatasetsLoader, FakeQuery]:
    """Provide a loader backed by representative raw records."""
    query = FakeQuery({
        "blueprints": [
            (
                1,
                {
                    "blueprintTypeID": 1,
                    "activities": {"manufacturing": {"time": 1}},
                },
            )
        ],
        "typeMaterials": [(2, {"materials": []})],
        "types": [
            (
                3,
                {
                    "groupID": 1,
                    "name": {"en": "Published"},
                    "portionSize": 1,
                    "published": True,
                },
            ),
            (
                4,
                {
                    "groupID": 1,
                    "name": {"en": "Unpublished"},
                    "portionSize": 1,
                    "published": False,
                },
            ),
        ],
        "metaGroups": [(5, {"name": {"en": "Tech"}})],
        "categories": [(6, {"name": {"en": "Ships"}, "published": True})],
        "groups": [
            (
                7,
                {
                    "anchorable": False,
                    "anchored": False,
                    "categoryID": 6,
                    "fittableNonSingleton": True,
                    "name": {"en": "Frigate"},
                    "published": True,
                    "useBasePrice": False,
                },
            )
        ],
    })
    return EsdDatasetsLoader(SimpleNamespace(query=query)), query


@pytest.mark.parametrize(
    ("method_name", "dataset_name"),
    [
        ("blueprints", "blueprints"),
        ("type_materials", "typeMaterials"),
        ("meta_groups", "metaGroups"),
        ("categories", "categories"),
        ("groups", "groups"),
    ],
)
def test_loaders_return_typed_dataset_and_query_expected_name(
    loader_and_query: tuple[EsdDatasetsLoader, FakeQuery],
    method_name: str,
    dataset_name: str,
) -> None:
    """Each accessor should preserve records and select its ESD dataset."""
    loader, query = loader_and_query

    result = getattr(loader, method_name)()

    assert set(result.dataset) == {key for key, _ in query.records[dataset_name]}
    assert query.calls == [dataset_name]


@pytest.mark.parametrize(
    ("published", "expected_ids"),
    [(True, {3}), (False, {4}), (None, {3, 4})],
)
def test_types_filters_by_published_flag(
    loader_and_query: tuple[EsdDatasetsLoader, FakeQuery],
    published: bool | None,
    expected_ids: set[int],
) -> None:
    """The types accessor should support published, unpublished, and all records."""
    loader, query = loader_and_query

    result = loader.types(published)

    assert set(result.dataset) == expected_ids
    assert query.calls == ["types"]


def test_types_rejects_invalid_published_value(
    loader_and_query: tuple[EsdDatasetsLoader, FakeQuery],
) -> None:
    """Invalid filter values should fail before returning an ambiguous dataset."""
    loader, query = loader_and_query

    with pytest.raises(ValueError, match="Must be True, False, or None"):
        loader.types(1)  # type: ignore[arg-type]

    assert query.calls == []
