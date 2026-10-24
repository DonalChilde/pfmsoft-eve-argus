"""Tests for offline market-group JSON and CSV exports."""

import csv
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from pfmsoft.eve_argus.cli import app
from pfmsoft.eve_argus.cli import helpers as cli_helpers
from pfmsoft.eve_argus.helpers import connection_helpers
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings
from pfmsoft.eve_argus.static.query_helpers import load_table_definitions
from pfmsoft.eve_argus.static.store import ManifestEntry, StaticManifest, StaticStore


@pytest.fixture
def settings(tmp_path: Path) -> EveArgusSettings:
    """Provide isolated settings and two builds in a temporary static store."""
    settings = Mock(spec=EveArgusSettings)
    settings.static_database_store = tmp_path / "store"
    settings.static_database_build_number = None
    settings.static_database_store.mkdir()
    entries: dict[int, ManifestEntry] = {}
    for build in (1, 2):
        path = settings.static_database_store / f"build-{build}.sqlite"
        with closing(sqlite3.connect(path)) as connection:
            connection.executescript(load_table_definitions())
            with connection:
                connection.execute(
                    """
                    INSERT INTO market_groups
                        (market_group_id, description, has_types, icon_id, name,
                         parent_group_id, int_path, str_path, types)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        4,
                        'A "quoted", description\nwith a newline',
                        0,
                        None,
                        f"Ships {build}",
                        None,
                        "[4]",
                        json.dumps([f"Ships {build}"]),
                        None,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO market_groups
                        (market_group_id, description, has_types, icon_id, name,
                         parent_group_id, int_path, str_path, types)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        9,
                        "Frigates",
                        1,
                        12,
                        'Frigates, "café"\nsmall',
                        4,
                        "[4, 9]",
                        json.dumps([f"Ships {build}", 'Frigates, "café"\nsmall']),
                        "[587, 588]",
                    ),
                )
        entries[build] = ManifestEntry(
            build_number=build, release_date="2026-10-20", file_name=path.name
        )
    (settings.static_database_store / "manifest.json").write_text(
        StaticManifest(entries=entries).serialize(), encoding="utf-8"
    )
    return settings


def test_exports_complete_dataset_in_both_formats(
    settings: EveArgusSettings, tmp_path: Path
) -> None:
    """Keep IDs, scalars, Unicode and containers intact through both formats."""
    destination = tmp_path / "output"
    database = settings.static_database_store / "build-2.sqlite"
    before = database.read_bytes()
    result = CliRunner().invoke(
        app,
        ["export", "market-groups", "--to", str(destination)],
        obj={SETTINGS_KEY: settings},
    )
    assert result.exit_code == 0, result.output
    assert {path.name for path in destination.iterdir()} == {
        "market-groups.json",
        "market-groups.csv",
    }
    dataset = json.loads((destination / "market-groups.json").read_text("utf-8"))
    assert list(dataset) == ["4", "9"]
    assert dataset["4"] == {
        "market_group_id": 4,
        "description": 'A "quoted", description\nwith a newline',
        "has_types": False,
        "icon_id": None,
        "int_path": [4],
        "name": "Ships 2",
        "parent_group_id": None,
        "str_path": ["Ships 2"],
        "types": [],
    }
    with (destination / "market-groups.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == list(dataset["4"])
        rows = list(reader)
    assert [row["market_group_id"] for row in rows] == ["4", "9"]
    for row in rows:
        record = dataset[row["market_group_id"]]
        for field in ("int_path", "types"):
            assert json.loads(row[field]) == record[field]
        assert row["str_path"] == "/".join(record["str_path"])
        for field in ("description", "name"):
            assert row[field] == record[field]
        for field in ("icon_id", "parent_group_id"):
            assert row[field] == ("" if record[field] is None else str(record[field]))
        assert row["has_types"] == str(record["has_types"])
    assert database.read_bytes() == before


def test_csv_is_sorted_by_rendered_string_path(
    settings: EveArgusSettings, tmp_path: Path
) -> None:
    """Sort CSV by its displayed path while retaining JSON's ID ordering."""
    with closing(
        sqlite3.connect(settings.static_database_store / "build-2.sqlite")
    ) as connection:
        with connection:
            connection.execute(
                "UPDATE market_groups SET str_path = ? WHERE market_group_id = 4",
                (json.dumps(["Zulu"]),),
            )
            connection.execute(
                "UPDATE market_groups SET str_path = ? WHERE market_group_id = 9",
                (json.dumps(["Alpha", "Frigates"]),),
            )
    destination = tmp_path / "output"
    result = CliRunner().invoke(
        app,
        ["export", "market-groups", "--to", str(destination)],
        obj={SETTINGS_KEY: settings},
    )
    assert result.exit_code == 0, result.output
    with (destination / "market-groups.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert [row["market_group_id"] for row in rows] == ["9", "4"]
    assert [row["str_path"] for row in rows] == ["Alpha/Frigates", "Zulu"]
    dataset = json.loads((destination / "market-groups.json").read_text("utf-8"))
    assert list(dataset) == ["4", "9"]


def test_explicit_build_and_quiet(settings: EveArgusSettings, tmp_path: Path) -> None:
    """Honor the configured build rather than always choosing the latest."""
    settings.static_database_build_number = 1
    destination = tmp_path / "output"
    result = CliRunner().invoke(
        app,
        ["export", "market-groups", "--to", str(destination), "--quiet"],
        obj={SETTINGS_KEY: settings},
    )
    assert result.exit_code == 0, result.output
    assert result.output == ""
    dataset = json.loads((destination / "market-groups.json").read_text())
    assert dataset["4"]["name"] == "Ships 1"


@pytest.mark.parametrize("filename", ["market-groups.json", "market-groups.csv"])
def test_existing_output_requires_overwrite(
    settings: EveArgusSettings, tmp_path: Path, filename: str
) -> None:
    """Preflight both filenames before replacing or creating either output."""
    destination = tmp_path / "output"
    destination.mkdir()
    existing = destination / filename
    existing.write_text("keep me")
    args = ["export", "market-groups", "--to", str(destination)]
    result = CliRunner().invoke(app, args, obj={SETTINGS_KEY: settings})
    assert result.exit_code == 1
    assert "--overwrite" in result.output
    assert existing.read_text() == "keep me"
    assert list(destination.iterdir()) == [existing]
    result = CliRunner().invoke(
        app, [*args, "--overwrite"], obj={SETTINGS_KEY: settings}
    )
    assert result.exit_code == 0, result.output
    assert existing.read_text() != "keep me"


def test_empty_dataset_retains_headers(
    settings: EveArgusSettings, tmp_path: Path
) -> None:
    """An existing empty dataset exports an empty object and header-only CSV."""
    with closing(
        sqlite3.connect(settings.static_database_store / "build-2.sqlite")
    ) as connection:
        with connection:
            connection.execute("DELETE FROM market_groups")
    destination = tmp_path / "output"
    result = CliRunner().invoke(
        app,
        ["export", "market-groups", "--to", str(destination)],
        obj={SETTINGS_KEY: settings},
    )
    assert result.exit_code == 0, result.output
    assert json.loads((destination / "market-groups.json").read_text()) == {}
    with (destination / "market-groups.csv").open(newline="") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == [
            "market_group_id",
            "description",
            "has_types",
            "icon_id",
            "int_path",
            "name",
            "parent_group_id",
            "str_path",
            "types",
        ]
        assert list(reader) == []


@pytest.mark.parametrize(
    "failure",
    [
        "missing-build",
        "missing-database",
        "manifest",
        "missing-manifest",
        "empty-manifest",
        "destination",
    ],
)
def test_errors_are_visible_without_outputs(
    settings: EveArgusSettings, tmp_path: Path, failure: str
) -> None:
    """Invalid source and output paths fail explicitly even with quiet enabled."""
    destination = tmp_path / "output"
    match failure:
        case "missing-build":
            settings.static_database_build_number = 99
        case "missing-database":
            settings.static_database_build_number = 99
            manifest = StaticManifest(
                entries={
                    99: ManifestEntry(
                        build_number=99,
                        release_date="2026-10-20",
                        file_name="missing.sqlite",
                    )
                }
            )
            (settings.static_database_store / "manifest.json").write_text(
                manifest.serialize()
            )
        case "manifest":
            (settings.static_database_store / "manifest.json").write_text("invalid")
        case "missing-manifest":
            settings.static_database_store = tmp_path / "missing-store"
        case "empty-manifest":
            (settings.static_database_store / "manifest.json").write_text(
                StaticManifest(entries={}).serialize()
            )
        case "destination":
            destination.write_text("not a directory")
        case _:
            pytest.fail(f"Unhandled failure case: {failure}")
    result = CliRunner().invoke(
        app,
        ["export", "market-groups", "--to", str(destination), "--quiet"],
        obj={SETTINGS_KEY: settings},
    )
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert not (settings.static_database_store / "missing.sqlite").exists()
    assert not destination.is_dir()


def test_database_is_opened_read_only(
    settings: EveArgusSettings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Use the read-only factory rather than just avoiding explicit write queries."""
    factory = Mock(wraps=connection_helpers.create_read_only_connection)
    monkeypatch.setattr(connection_helpers, "create_read_only_connection", factory)
    result = CliRunner().invoke(
        app,
        ["export", "market-groups", "--to", str(tmp_path / "output")],
        obj={SETTINGS_KEY: settings},
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(
        settings.static_database_store / "build-2.sqlite", row_factory=None
    )


@pytest.mark.parametrize(
    ("build_number", "resolved"), [(None, 2), (1, 1)], ids=["latest", "explicit"]
)
def test_database_path_is_resolved_through_static_store(
    settings: EveArgusSettings,
    monkeypatch: pytest.MonkeyPatch,
    build_number: int | None,
    resolved: int,
) -> None:
    """Resolve the manifest entry, then request its path by resolved build number."""
    settings.static_database_build_number = build_number
    factory = Mock()
    factory.MANIFEST_FILE_NAME = StaticStore.MANIFEST_FILE_NAME
    factory.return_value.get_entry.return_value = Mock(build_number=resolved)
    expected = settings.static_database_store / "selected.sqlite"
    factory.return_value.get_file_path_for_entry.return_value = expected
    monkeypatch.setattr(cli_helpers, "StaticStore", factory)

    assert cli_helpers.get_static_database_path(settings) == expected

    factory.assert_called_once_with(store_path=settings.static_database_store)
    factory.return_value.get_entry.assert_called_once_with(build_number)
    factory.return_value.get_file_path_for_entry.assert_called_once_with(
        build_number=resolved
    )


def test_unknown_build_is_explicit_error(settings: EveArgusSettings) -> None:
    """A build absent from the manifest names the configured build number."""
    settings.static_database_build_number = 99

    with pytest.raises(
        ValueError, match="No static database manifest entry for build 99"
    ):
        cli_helpers.get_static_database_path(settings)


def test_missing_manifest_is_not_created(
    settings: EveArgusSettings, tmp_path: Path
) -> None:
    """Export path resolution must not initialize an existing empty store."""
    settings.static_database_store = tmp_path / "empty-store"
    settings.static_database_store.mkdir()

    with pytest.raises(FileNotFoundError, match="Manifest file not found"):
        cli_helpers.get_static_database_path(settings)

    assert list(settings.static_database_store.iterdir()) == []


@pytest.mark.parametrize("filename", ["market-groups.json", "market-groups.csv"])
def test_overwrite_rejects_output_directory(
    settings: EveArgusSettings, tmp_path: Path, filename: str
) -> None:
    """Overwrite permission never replaces a directory or writes its sibling."""
    destination = tmp_path / "output"
    existing = destination / filename
    existing.mkdir(parents=True)
    result = CliRunner().invoke(
        app,
        ["export", "market-groups", "--to", str(destination), "--overwrite"],
        obj={SETTINGS_KEY: settings},
    )
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert list(destination.iterdir()) == [existing]


def test_filesystem_failure_is_reported(
    settings: EveArgusSettings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Filesystem failures return an error rather than claiming a successful export."""
    destination = tmp_path / "output"
    monkeypatch.setattr(
        Path, "mkdir", Mock(side_effect=PermissionError("Export is not writable"))
    )
    result = CliRunner().invoke(
        app,
        ["export", "market-groups", "--to", str(destination), "--quiet"],
        obj={SETTINGS_KEY: settings},
    )
    assert result.exit_code == 1
    assert "Export is not writable" in result.output
    assert not destination.exists()
