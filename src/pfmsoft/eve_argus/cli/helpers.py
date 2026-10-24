"""Helpers for the CLI."""

import sys
from pathlib import Path
from typing import cast

import typer

from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings
from pfmsoft.eve_argus.static.store import StaticStore


def get_static_database_path(settings: EveArgusSettings) -> Path:
    """Resolve the configured static build's database path without writing to the store.

    The configured build number is used, or the latest manifest build when unset.

    Args:
        settings: Settings providing the static store path and build number.

    Returns:
        The database file path for the resolved build.

    Raises:
        FileNotFoundError: If the store exists but has no manifest file; a manifest is
            never created by this read-only lookup.
        ValueError: If the manifest has no entry for the configured build.
    """
    store_path = settings.static_database_store
    manifest_path = store_path / StaticStore.MANIFEST_FILE_NAME
    if store_path.is_dir() and not manifest_path.exists():
        raise FileNotFoundError(f"Manifest file not found at {manifest_path}")
    store = StaticStore(store_path=store_path)
    entry = store.get_entry(settings.static_database_build_number)
    if entry is None:
        raise ValueError(
            f"No static database manifest entry for build {settings.static_database_build_number}"
        )
    return store.get_file_path_for_entry(build_number=entry.build_number)


def get_stdin() -> str:
    """Read piped or redirected stdin content until EOF.

    Returns:
        Full stdin content as a string.

    Raises:
        ValueError: If stdin is attached to an interactive terminal instead
            of a pipe or redirected input source.
    """
    if sys.stdin.isatty():
        raise ValueError("Error: provide a file path or pipe data via stdin.")
    return sys.stdin.read()


def get_eve_argus_settings_from_context(ctx: typer.Context) -> EveArgusSettings:
    """Retrieve the Eve Argus settings from the Typer context.

    Args:
        ctx: The Typer context object.

    Returns:
        The Eve Argus settings.
    """
    settings = cast(EveArgusSettings, ctx.obj.get(SETTINGS_KEY))
    return settings
