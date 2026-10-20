"""Helpers for the CLI."""

import sys
from pathlib import Path
from typing import cast

import typer

from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings
from pfmsoft.eve_argus.static.store import StaticStore


def get_static_database_path(settings: EveArgusSettings) -> Path:
    """Resolve the configured build through StaticStore without creating a manifest."""
    store = StaticStore(store_path=settings.static_database_store)
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
