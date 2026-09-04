"""Shared helpers for the ESI data proof scripts.

Provides the common output and logging paths, loader construction, and sample
auth data loading used by the individual proof scripts in this directory.
Paths are resolved relative to this file so that all scripts keep writing to
the same proof-output and logging directories as the original combined script.
"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from logging import basicConfig
from pathlib import Path
from typing import TypedDict
from uuid import UUID

from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.settings import get_settings

PROOF_OUTPUT_DIR = Path(__file__).parent.parent / "proof-output" / "esi-data-loader"
PROOF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DEV_SECRETS_DIR = Path(__file__).parent.parent.parent / "secrets"
LOGGING_DIR = Path(__file__).parent.parent / "logging"
LOGGING_DIR.mkdir(parents=True, exist_ok=True)


class SampleAuthData(TypedDict):
    """Sample authenticated identity used by authorized ESI endpoints."""

    character_id: int
    corporation_id: int
    cred_id: UUID


def setup_logging(script_name: str) -> Path:
    """Configure logging to a script-specific file in the shared logging dir.

    Args:
        script_name: Base name of the proof script, used as the log file name.

    Returns:
        The path to the log file.
    """
    log_filepath = LOGGING_DIR / f"{script_name}.log"
    basicConfig(filename=log_filepath, level="INFO")
    return log_filepath


@asynccontextmanager
async def create_resources() -> AsyncGenerator[EveArgusResources]:
    """Yield managed EveArgusResources for scripts needing both ESI and ESD access.

    Yields:
        An open EveArgusResources (esi link, esi schema, and static data query manager).
    """
    settings = get_settings()
    print(f"Using settings: {settings}")
    resource_manager = EveArgusResources(settings=settings)
    async with resource_manager as resources:
        yield resources


def get_sample_auth_data() -> SampleAuthData | None:
    """Loads sample auth data from the secrets directory.

    Returns:
        The sample auth data, or None if the secrets file does not exist.
    """
    sample_auth_filepath = DEV_SECRETS_DIR / "auth.json"
    if not sample_auth_filepath.exists():
        print(f"Sample auth file {sample_auth_filepath} does not exist.")
        return None
    sample_auth_data = json.loads(sample_auth_filepath.read_text())
    return SampleAuthData(
        character_id=sample_auth_data["character_id"],
        corporation_id=sample_auth_data["corporation_id"],
        cred_id=UUID(sample_auth_data["cred_id"]),
    )
