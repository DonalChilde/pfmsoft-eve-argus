"""Common ESI-only resources and output helpers for the new ESI proofs."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Coroutine, Sized
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from uuid import UUID

from pfmsoft.eve_link import (
    EsiLink,
    EsiResponse,
    EsiSchema,
    FailedEsiResponse,
    SimpleRequests,
)

from pfmsoft.eve_argus.esi.models import EsiResponseBaseModel
from pfmsoft.eve_argus.settings import get_settings

PROOF_OUTPUT_DIR = Path(__file__).parent.parent / "proof-output" / "esi-data-new"
LOGGING_DIR = Path(__file__).parent.parent / "logging" / "esi-data-new"
DEV_SECRETS_DIR = Path(__file__).parent.parent.parent / "secrets"


@dataclass(slots=True, kw_only=True)
class SampleAuthData:
    """Identity and credential reference for authenticated corporation requests."""

    character_id: int
    corporation_id: int
    credential_id: UUID


@dataclass(slots=True, kw_only=True)
class EsiResources:
    """The ESI client and schema, without unrelated database resources."""

    esi_link: EsiLink
    esi_schema: EsiSchema


@asynccontextmanager
async def create_resources() -> AsyncGenerator[EsiResources]:
    """Open an ESI client using the same development settings as the old proofs."""
    settings = get_settings()
    requests = SimpleRequests(settings=settings.eve_link_settings)
    schema = requests.get_schema(compatibility_date=settings.compatibility_date)
    async with requests.esi_link_factory() as esi_link:
        yield EsiResources(esi_link=esi_link, esi_schema=schema)


def get_sample_auth_data() -> SampleAuthData:
    """Load identity references from dev secrets, failing if absent or invalid."""
    filepath = DEV_SECRETS_DIR / "auth.json"
    data = json.loads(filepath.read_text(encoding="utf-8"))
    return SampleAuthData(
        character_id=int(data["character_id"]),
        corporation_id=int(data["corporation_id"]),
        credential_id=UUID(data["cred_id"]),
    )


def save_raw_response(
    response: EsiResponse | FailedEsiResponse, *, name: str
) -> EsiResponse:
    """Reject failed fetches and preserve raw endpoint data before validation."""
    if isinstance(response, FailedEsiResponse):
        message = f"{name}: {response.failed_response.error_messages}"
        logging.getLogger(__name__).error(message)
        raise RuntimeError(message)
    PROOF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = PROOF_OUTPUT_DIR / f"{name}-raw.json"
    filename.write_text(json.dumps(response.response_data, indent=2), encoding="utf-8")
    print(f"Saved raw response to {filename}")
    return response


def save_validated_response(model: EsiResponseBaseModel, *, name: str) -> None:
    """Persist the new validated model separately from the raw endpoint data."""
    PROOF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = PROOF_OUTPUT_DIR / f"{name}-validated.json"
    filename.write_text(model.serialize(indent=2), encoding="utf-8")
    counts = {
        key: len(value)
        for key, value in model.model_dump().items()
        if isinstance(value, Sized) and not isinstance(value, (str, bytes))
    }
    print(f"Saved validated response to {filename}; record counts: {counts}")


def run_proof(proof: Coroutine[None, None, None], *, name: str) -> None:
    """Configure isolated logging and run one timed proof, propagating failures."""
    LOGGING_DIR.mkdir(parents=True, exist_ok=True)
    log_filepath = LOGGING_DIR / f"{name}.log"
    logging.basicConfig(
        filename=log_filepath,
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    print(f"Logging to {log_filepath}")
    start = perf_counter()
    asyncio.run(proof)
    print(f"{name} completed in {perf_counter() - start:.6f} seconds")
