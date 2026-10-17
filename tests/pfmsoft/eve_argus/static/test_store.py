"""Test manifest serialization and static store operations in temporary directories."""

from pathlib import Path
from sqlite3 import connect

import pytest
from pydantic import ValidationError

from pfmsoft.eve_argus.static.store import ManifestEntry, StaticManifest, StaticStore

_RELEASE = "2026-08-11T11:11:17Z"


@pytest.mark.parametrize("empty", [False, True], ids=["entries", "empty"])
def test_manifest_round_trip(*, empty: bool) -> None:
    """Preserve typed entries and integer build keys in JSON."""
    entries = (
        {}
        if empty
        else {
            123: ManifestEntry(
                build_number=123, release_date=_RELEASE, file_name="build.sqlite"
            )
        }
    )
    manifest = StaticManifest(entries=entries)

    assert StaticManifest.deserialize(manifest.serialize()) == manifest


@pytest.mark.parametrize("text", ["not json", '{"entries": {"123": {}}}'])
def test_manifest_rejects_invalid_data(text: str) -> None:
    """Malformed JSON and incomplete entries fail validation explicitly."""
    with pytest.raises(ValidationError):
        StaticManifest.deserialize(text)


def test_store_requires_existing_directory(tmp_path: Path) -> None:
    """Reject missing paths and files rather than creating an unintended store."""
    with pytest.raises(FileNotFoundError, match="Store path not found"):
        StaticStore(tmp_path / "missing")
    file_path = tmp_path / "file"
    file_path.touch()
    with pytest.raises(NotADirectoryError, match="not a directory"):
        StaticStore(file_path)


def test_new_store_creates_empty_manifest(tmp_path: Path) -> None:
    """Initialize an empty manifest and report absent builds clearly."""
    store = StaticStore(tmp_path)

    assert store.manifest == StaticManifest(entries={})
    assert StaticManifest.deserialize(store.manifest_path.read_text()) == store.manifest
    assert store.get_entry(None) is None
    assert store.get_entry(123) is None
    with pytest.raises(ValueError, match="No entry found"):
        store.get_file_path_for_entry(None)


def test_store_add_entry_initializes_schema(tmp_path: Path) -> None:
    """Adding an entry creates a SQLite schema and persists its relative filename."""
    store = StaticStore(tmp_path)

    store.add_entry(123, _RELEASE)

    path = store.get_file_path_for_entry(123)
    assert path.parent == tmp_path
    assert path.is_file()
    entry = store.get_entry(123)
    assert entry is not None
    assert entry.file_name == path.name
    assert entry.release_date == _RELEASE
    assert ":" not in path.name
    assert StaticManifest.deserialize(store.manifest_path.read_text()) == store.manifest
    connection = connect(path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"types", "blueprints", "sde_metadata", "industry_activities"} <= tables
    finally:
        connection.close()


def test_store_reopens_relative_entry_from_other_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resolve stored filenames relative to the store, never the process directory."""
    store_path = tmp_path / "store"
    store_path.mkdir()
    store = StaticStore(store_path)
    store.add_entry(123, _RELEASE)
    monkeypatch.chdir(tmp_path)

    reopened = StaticStore(store_path)

    assert reopened.get_file_path_for_entry(123) == store.get_file_path_for_entry(123)


def test_store_selects_highest_build_not_insertion_order(tmp_path: Path) -> None:
    """The default entry is the highest build number, not the last one added."""
    store = StaticStore(tmp_path)
    store.add_entry(200, _RELEASE)
    store.add_entry(100, _RELEASE)

    assert store.get_entry(None) == store.get_entry(200)
    assert store.get_file_path_for_entry(None) == store.get_file_path_for_entry(200)


def test_store_rejects_duplicate_build(tmp_path: Path) -> None:
    """Do not modify the manifest when the build already exists."""
    store = StaticStore(tmp_path)
    store.add_entry(123, _RELEASE)
    before = store.manifest_path.read_text()

    with pytest.raises(ValueError, match="Entry already exists"):
        store.add_entry(123, "another-release")

    assert store.manifest_path.read_text() == before


def test_store_rejects_existing_database_file(tmp_path: Path) -> None:
    """Do not adopt or change an untracked database already occupying the target path."""
    store = StaticStore(tmp_path)
    path = tmp_path / store.file_name_for_new_entry(123, _RELEASE)
    path.write_bytes(b"existing file")

    with pytest.raises(FileExistsError, match="File already exists"):
        store.add_entry(123, _RELEASE)

    assert path.read_bytes() == b"existing file"
    assert store.manifest.entries == {}


def test_store_reports_missing_linked_file(tmp_path: Path) -> None:
    """A manifest with a missing linked database fails at store initialization."""
    manifest = StaticManifest(
        entries={
            123: ManifestEntry(
                build_number=123, release_date=_RELEASE, file_name="missing.sqlite"
            )
        }
    )
    (tmp_path / "manifest.json").write_text(manifest.serialize())

    with pytest.raises(FileNotFoundError, match="File not found for entry"):
        StaticStore(tmp_path)


def test_store_remove_entry_persists_and_deletes_only_target(tmp_path: Path) -> None:
    """Remove the requested database and entry, preserving all other files."""
    store = StaticStore(tmp_path)
    store.add_entry(100, _RELEASE)
    store.add_entry(200, _RELEASE)
    removed_path = store.get_file_path_for_entry(100)
    retained_path = store.get_file_path_for_entry(200)

    store.remove_entry(100)

    assert not removed_path.exists()
    assert retained_path.is_file()
    assert store.get_entry(100) is None
    assert set(StaticManifest.deserialize(store.manifest_path.read_text()).entries) == {
        200
    }


def test_store_remove_absent_entry_is_noop(tmp_path: Path) -> None:
    """Removing an unknown build leaves the manifest unchanged."""
    store = StaticStore(tmp_path)
    before = store.manifest_path.read_text()

    store.remove_entry(123)

    assert store.manifest_path.read_text() == before
