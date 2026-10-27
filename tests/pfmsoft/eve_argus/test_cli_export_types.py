"""Tests for offline static type CSV exports."""

import csv
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from pfmsoft.eve_argus.cli import app
from pfmsoft.eve_argus.helpers import connection_helpers
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings
from pfmsoft.eve_argus.static.store import ManifestEntry, StaticManifest
from pfmsoft.eve_argus.static.util import load_table_definitions


@pytest.fixture
def settings(tmp_path: Path) -> EveArgusSettings:
    """Provide two isolated static builds with linked type metadata."""
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
                    "INSERT INTO sde_metadata VALUES (?, ?)",
                    (9000 + build, "2026-10-20"),
                )
                connection.executemany(
                    """
                    INSERT INTO categories (category_id, name, published)
                    VALUES (?, ?, ?)
                    """,
                    [(6, "Ships", 1)],
                )
                connection.executemany(
                    """
                    INSERT INTO groups (
                        group_id, anchorable, anchored, category_id,
                        fittable_non_singleton, name, published, use_base_price
                    )
                    VALUES (?, 0, 0, 6, 0, ?, ?, 0)
                    """,
                    [(5, "Frigate", 1), (7, "Unpublished group", 0)],
                )
                connection.executemany(
                    """
                    INSERT INTO market_groups (
                        market_group_id, description, has_types, name,
                        parent_group_id, int_path, str_path
                    )
                    VALUES (?, '', ?, ?, ?, ?, ?)
                    """,
                    [
                        (10, 0, "Ships", None, "[10]", '["Ships"]'),
                        (
                            11,
                            1,
                            "Frigates",
                            10,
                            "[10, 11]",
                            '["Ships", "Frigates"]',
                        ),
                    ],
                )
                connection.execute(
                    """
                    INSERT INTO meta_groups
                        (meta_group_id, name)
                    VALUES (2, 'Tech II')
                    """
                )
                connection.executemany(
                    """
                    INSERT INTO types (
                        type_id, description, group_id, market_group_id,
                        meta_group_id, name, portion_size, published,
                        is_dynamic_type, is_repackable
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?, 0, 1)
                    """,
                    [
                        (
                            11,
                            'Quoted, "description"\nwith café',
                            5,
                            11,
                            2,
                            "Linked type",
                            1,
                        ),
                        (12, "No optional groups", 5, None, None, "Basic type", 1),
                        (13, "Unpublished group", 7, 11, None, "Odd type", 1),
                        (14, "Unpublished type", 5, 11, 2, "Hidden type", 0),
                    ],
                )
        entries[build] = ManifestEntry(
            build_number=build, release_date="2026-10-20", file_name=path.name
        )
    (settings.static_database_store / "manifest.json").write_text(
        StaticManifest(entries=entries).serialize(), encoding="utf-8"
    )
    return settings


def test_exports_type_fields_and_linked_names(
    settings: EveArgusSettings, tmp_path: Path
) -> None:
    """Export linked names, a market-group path, and description as the final field."""
    destination = tmp_path / "output"
    result = CliRunner().invoke(
        app,
        ["export", "types", "--to", str(destination)],
        obj={SETTINGS_KEY: settings},
    )
    assert result.exit_code == 0, result.output
    output_path = destination / "types-build-9002.csv"
    with output_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == [
            "type_id",
            "base_price",
            "capacity",
            "faction_id",
            "graphic_id",
            "group_id",
            "group_name",
            "category_id",
            "category_name",
            "icon_id",
            "is_dynamic_type",
            "is_repackable",
            "market_group_id",
            "market_group_name",
            "mass",
            "meta_group_id",
            "meta_group_name",
            "meta_level",
            "name",
            "packaged_volume",
            "portion_size",
            "published",
            "race_id",
            "radius",
            "ship_tree_group_id",
            "sound_id",
            "tech_level",
            "variation_parent_type_id",
            "volume",
            "market_group_path",
            "description",
        ]
        rows = list(reader)

    assert [row["type_id"] for row in rows] == ["11", "12", "13"]
    assert rows[0] == {
        "type_id": "11",
        "base_price": "",
        "capacity": "",
        "faction_id": "",
        "graphic_id": "",
        "group_id": "5",
        "group_name": "Frigate",
        "category_id": "6",
        "category_name": "Ships",
        "icon_id": "",
        "is_dynamic_type": "False",
        "is_repackable": "True",
        "market_group_id": "11",
        "market_group_name": "Frigates",
        "mass": "",
        "meta_group_id": "2",
        "meta_group_name": "Tech II",
        "meta_level": "",
        "name": "Linked type",
        "packaged_volume": "",
        "portion_size": "1",
        "published": "True",
        "race_id": "",
        "radius": "",
        "ship_tree_group_id": "",
        "sound_id": "",
        "tech_level": "",
        "variation_parent_type_id": "",
        "volume": "",
        "market_group_path": "Ships/Frigates",
        "description": 'Quoted, "description"\nwith café',
    }
    assert rows[1]["market_group_name"] == ""
    assert rows[1]["market_group_path"] == ""
    assert rows[1]["meta_group_name"] == ""
    assert rows[2]["group_name"] == "Unpublished group"
    assert rows[2]["category_name"] == "Ships"


def test_include_unpublished_and_metadata_build_number(
    settings: EveArgusSettings, tmp_path: Path
) -> None:
    """Include unpublished types on request and use the SDE build in the filename."""
    settings.static_database_build_number = 1
    destination = tmp_path / "output"
    result = CliRunner().invoke(
        app,
        ["export", "types", "--to", str(destination), "--include-unpublished"],
        obj={SETTINGS_KEY: settings},
    )
    assert result.exit_code == 0, result.output
    assert {path.name for path in destination.iterdir()} == {"types-build-9001.csv"}
    with (destination / "types-build-9001.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert [row["type_id"] for row in rows] == ["11", "12", "13", "14"]


def test_requires_overwrite_and_quiet_mode(
    settings: EveArgusSettings, tmp_path: Path
) -> None:
    """Protect existing build-specific output unless overwrite is enabled."""
    destination = tmp_path / "output"
    destination.mkdir()
    output_path = destination / "types-build-9002.csv"
    output_path.write_text("preserve", encoding="utf-8")
    args = ["export", "types", "--to", str(destination)]
    result = CliRunner().invoke(app, args, obj={SETTINGS_KEY: settings})
    assert result.exit_code == 1
    assert "--overwrite" in result.output
    assert output_path.read_text(encoding="utf-8") == "preserve"

    result = CliRunner().invoke(
        app, [*args, "--overwrite", "--quiet"], obj={SETTINGS_KEY: settings}
    )
    assert result.exit_code == 0, result.output
    assert result.output == ""
    assert output_path.read_text(encoding="utf-8") != "preserve"


def test_database_is_opened_read_only(
    settings: EveArgusSettings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Open the static database through the existing read-only connection factory."""
    factory = Mock(wraps=connection_helpers.create_read_only_connection)
    monkeypatch.setattr(connection_helpers, "create_read_only_connection", factory)
    result = CliRunner().invoke(
        app,
        ["export", "types", "--to", str(tmp_path / "output")],
        obj={SETTINGS_KEY: settings},
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(
        settings.static_database_store / "build-2.sqlite", row_factory=None
    )


def test_missing_sde_metadata_is_reported(
    settings: EveArgusSettings, tmp_path: Path
) -> None:
    """Fail explicitly when the selected database has no SDE metadata row."""
    with closing(
        sqlite3.connect(settings.static_database_store / "build-2.sqlite")
    ) as connection:
        with connection:
            connection.execute("DELETE FROM sde_metadata")
    destination = tmp_path / "output"
    result = CliRunner().invoke(
        app,
        ["export", "types", "--to", str(destination), "--quiet"],
        obj={SETTINGS_KEY: settings},
    )
    assert result.exit_code == 1
    assert "SDE metadata not found" in result.output
    assert not destination.exists()
