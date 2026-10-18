"""Shared helpers for fetch commands."""

from math import ceil
from uuid import UUID

import typer
from rich.console import Console
from whenever import Instant

from pfmsoft.eve_argus.fetch_esi.update import Expirable, UpdateResult, UpdateStatus
from pfmsoft.eve_argus.settings import EveArgusSettings


def report_update_result[T: Expirable](
    result: UpdateResult[T],
    *,
    messenger: Console,
    dataset_name: str,
) -> T:
    """Report an update result and return the current response state."""
    if result.status is UpdateStatus.FAILED:
        messenger.print(
            f"Failed to fetch {dataset_name}: "
            f"{result.failure_message or 'Update failed.'}"
        )
        raise typer.Exit(code=1)

    if result.status is UpdateStatus.SKIPPED:
        messenger.print(f"Using cached {dataset_name}...")
        response = result.previous_state
        messenger.print(f"\tThe stored dataset for {dataset_name} is already current.")
    else:
        response = result.new_state
    if response is None:
        messenger.print(f"No {dataset_name} response is available after update.")
        raise typer.Exit(code=1)

    expiration = response.argus_expires_at or response.expires_at
    if expiration is None:
        messenger.print("\tDataset expiration is unavailable.")
    else:
        seconds_until_expiration = (
            Instant.parse_iso(expiration) - Instant.now()
        ).total("seconds")
        if seconds_until_expiration >= 0:
            messenger.print(
                f"\tDataset expires in {ceil(seconds_until_expiration)} seconds."
            )
        else:
            messenger.print(
                f"\tDataset expired {ceil(-seconds_until_expiration)} seconds ago."
            )
    if result.status is not UpdateStatus.SKIPPED:
        messenger.print(f"\tFetched and stored {dataset_name}.")
    return response


def resolve_corporation_arguments(
    *,
    settings: EveArgusSettings,
    corporation_id: int | None,
    character_id: int | None,
    credential_id: UUID | None,
) -> tuple[int, int, UUID]:
    """Resolve corporation command arguments from explicit values or defaults."""
    resolved_corporation_id = (
        settings.corporation_id if corporation_id is None else corporation_id
    )
    if resolved_corporation_id is None:
        raise typer.BadParameter(
            "Provide --corporation-id or configure default_ids.corporation_id."
        )

    resolved_character_id = (
        settings.character_id if character_id is None else character_id
    )
    if resolved_character_id is None:
        raise typer.BadParameter(
            "Provide --character-id or configure default_ids.character_id."
        )

    resolved_credential_id = (
        settings.credential_id if credential_id is None else credential_id
    )
    if resolved_credential_id is None:
        raise typer.BadParameter(
            "Provide --credential-id or configure default_ids.credential_id."
        )
    return resolved_corporation_id, resolved_character_id, resolved_credential_id
