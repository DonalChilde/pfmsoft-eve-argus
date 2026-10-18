"""Fetch corporation blueprint data."""

import asyncio
from typing import Annotated
from uuid import UUID

import typer
from rich.console import Console

from pfmsoft.eve_argus.cli.fetch._helpers import (
    report_update_result,
    resolve_corporation_arguments,
)
from pfmsoft.eve_argus.cli.helpers import get_eve_argus_settings_from_context
from pfmsoft.eve_argus.dynamic import read
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.fetch_esi import update_corporation_blueprints
from pfmsoft.eve_argus.fetch_esi.update import UpdateStatus
from pfmsoft.eve_argus.settings import EveArgusSettings

app = typer.Typer(no_args_is_help=True)


@app.command(name="corporation-blueprints")
def fetch_corporation_blueprints(
    ctx: typer.Context,
    corporation_id: Annotated[
        int | None,
        typer.Option(
            "--corporation-id",
            help="The ID of the corporation to fetch blueprints for. If not provided, defaults to the default corporation.",
            show_default=True,
        ),
    ] = None,
    character_id: Annotated[
        int | None,
        typer.Option(
            "--character-id",
            help="The ID of the character performing the fetch. If not provided, defaults to the default character.",
            show_default=True,
        ),
    ] = None,
    credential_id: Annotated[
        UUID | None,
        typer.Option(
            "--credential-id",
            help="The UUID of the credential to use, or the configured default.",
            show_default=True,
        ),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            help="Suppress messages.",
            show_default=True,
        ),
    ] = False,
) -> None:
    """Fetch corporation blueprints into the dynamic database."""
    settings = get_eve_argus_settings_from_context(ctx)
    ids = resolve_corporation_arguments(
        settings=settings,
        corporation_id=corporation_id,
        character_id=character_id,
        credential_id=credential_id,
    )
    messenger = Console(stderr=True, quiet=quiet)
    asyncio.run(
        _fetch_corporation_blueprints(
            settings=settings,
            corporation_id=ids[0],
            character_id=ids[1],
            credential_id=ids[2],
            messenger=messenger,
        )
    )


async def _fetch_corporation_blueprints(
    *,
    settings: EveArgusSettings,
    corporation_id: int,
    character_id: int,
    credential_id: UUID,
    messenger: Console,
) -> None:
    """Fetch corporation blueprints and report the result."""
    messenger.print(f"Checking blueprints for corporation {corporation_id}...")
    async with EveArgusResources(settings) as resources:
        result = await update_corporation_blueprints(
            resources.esi_link,
            resources.esi_schema,
            resources.argus_dynamic_db_connection,
            corporation_id=corporation_id,
            character_id=character_id,
            credential_id=credential_id,
        )
        response = report_update_result(
            result, messenger=messenger, dataset_name="corporation blueprints"
        )
        if result.status is not UpdateStatus.SKIPPED:
            blueprints = read.corporation_blueprints(
                resources.argus_dynamic_db_connection,
                response_metadata_id=response.response_metadata_id,
            )
            messenger.print(
                f"\tRead {len(blueprints.records)} blueprints from the database."
            )
