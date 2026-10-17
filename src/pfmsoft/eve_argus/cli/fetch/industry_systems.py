"""Fetch industry system cost indices."""

import asyncio
from typing import Annotated

import typer
from rich.console import Console

from pfmsoft.eve_argus.cli.fetch._helpers import report_update_result
from pfmsoft.eve_argus.cli.helpers import get_eve_argus_settings_from_context
from pfmsoft.eve_argus.dynamic import read
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.fetch_esi import update_system_cost_indices
from pfmsoft.eve_argus.fetch_esi.update import UpdateStatus
from pfmsoft.eve_argus.settings import EveArgusSettings

app = typer.Typer(no_args_is_help=True)


@app.command(name="industry-systems")
def fetch_industry_systems(
    ctx: typer.Context,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            help="Suppress messages.",
            show_default=True,
        ),
    ] = False,
) -> None:
    """Fetch industry system cost indices into the dynamic database."""
    settings = get_eve_argus_settings_from_context(ctx)
    messenger = Console(stderr=True, quiet=quiet)
    asyncio.run(_fetch_industry_systems(settings=settings, messenger=messenger))


async def _fetch_industry_systems(
    *, settings: EveArgusSettings, messenger: Console
) -> None:
    """Fetch industry system cost indices and report the result."""
    messenger.print("Checking industry system cost indices...")
    async with EveArgusResources(settings) as resources:
        result = await update_system_cost_indices(
            resources.esi_link,
            resources.esi_schema,
            resources.argus_dynamic_db_connection,
        )
        response = report_update_result(
            result, messenger=messenger, dataset_name="industry system cost indices"
        )
        if result.status is not UpdateStatus.SKIPPED:
            indices = read.system_cost_indices(
                resources.argus_dynamic_db_connection,
                response_metadata_id=response.response_metadata_id,
            )
            messenger.print(
                f"\tRead {len(indices.records)} system cost indices from the database."
            )
