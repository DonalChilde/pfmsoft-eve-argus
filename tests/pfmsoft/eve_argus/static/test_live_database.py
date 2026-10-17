"""Integration checks for a static database generated from a real ESD export.

Requires ``--esd-static-db PATH``; omitted paths skip these tests automatically.
Run from the repository root:

    uv run pytest tests/pfmsoft/eve_argus/static \
        --esd-static-db dev/tmp/sde-db/eve_static_data_3464040_yaml.db

The session-scoped ``argus_static_db_path`` fixture builds a temporary database
once. ``argus_static_db_connection`` opens a fresh read-only connection per test.
Neither the source export nor development Argus databases are modified.
"""

from pathlib import Path
from sqlite3 import Connection, OperationalError

import pytest
from pfmsoft.eve_sd import EveSdDbQueryManager

from pfmsoft.eve_argus.static import read


def test_live_database_round_trip(
    argus_static_db_path: Path,
    argus_static_db_connection: Connection,
    esd_static_db_path: Path,
) -> None:
    """Preserve source record IDs, publication flags, and normalized build metadata."""
    connection = argus_static_db_connection
    assert argus_static_db_path.resolve() != esd_static_db_path.resolve()
    with EveSdDbQueryManager(esd_static_db_path) as source:
        for name, reader in (
            ("categories", read.categories),
            ("groups", read.groups),
            ("types", read.types),
        ):
            expected = dict(source.query.get_int_records(name))
            actual = reader(connection, only_published=False)
            assert expected, name
            assert set(actual) == set(expected), name
            published_ids = {
                key for key, record in expected.items() if record["published"]
            }
            assert {
                key for key, record in actual.items() if record.published
            } == published_ids, name
            assert set(reader(connection)) == published_ids, name
        for name, reader in (
            ("industryActivities", read.industry_activities),
            ("mapConstellations", read.map_constellations),
            ("mapRegions", read.map_regions),
            ("mapSolarSystems", read.map_solar_systems),
            ("marketGroups", read.market_groups),
            ("metaGroups", read.meta_groups),
        ):
            expected = dict(source.query.get_int_records(name))
            actual = reader(connection)
            assert expected, name
            assert set(actual) == set(expected), name
        materials = dict(source.query.get_int_records("typeMaterials"))
        assert set(read.type_materials(connection)) == {
            key for key, record in materials.items() if record.get("materials")
        }
        assert set(read.type_materials_randomized(connection)) == {
            key
            for key, record in materials.items()
            if record.get("randomizedMaterials")
        }
        metadata = read.sde_metadata(connection)
        assert metadata.build_number == source.query.sde_metadata.buildNumber
        assert metadata.release_date == source.query.sde_metadata.releaseDate
        types = dict(source.query.get_int_records("types"))
        blueprint_ids = {
            row[0]
            for row in connection.execute("SELECT blueprint_type_id FROM blueprints")
        }
        assert blueprint_ids
        assert blueprint_ids <= {
            key
            for key, _ in source.query.get_int_records("blueprints")
            if key in types and types[key]["published"]
        }
    assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_live_connection_is_read_only(argus_static_db_connection: Connection) -> None:
    """Protect the shared fixture database from mutations by consuming tests."""
    with pytest.raises(OperationalError, match="readonly"):
        argus_static_db_connection.execute("DELETE FROM sde_metadata")
