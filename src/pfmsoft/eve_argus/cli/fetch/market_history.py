"""Fetch market history for one region and item type."""

import asyncio
from typing import Annotated

import typer
from rich.console import Console

from pfmsoft.eve_argus.cli.fetch._helpers import report_update_result
from pfmsoft.eve_argus.cli.helpers import get_eve_argus_settings_from_context
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.fetch_esi import update_market_history
from pfmsoft.eve_argus.fetch_esi.update import UpdateStatus
from pfmsoft.eve_argus.settings import EveArgusSettings

app = typer.Typer(no_args_is_help=True)


@app.command(name="market-history")
def fetch_market_history(
    ctx: typer.Context,
    region_id: Annotated[
        int,
        typer.Option("--region-id", help="The region ID to fetch history for."),
    ],
    type_id: Annotated[
        int,
        typer.Option("--type-id", help="The item type ID to fetch history for."),
    ],
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Suppress progress messages, but not errors."),
    ] = False,
) -> None:
    """Fetch one region/type pair into the market-history database."""
    settings = get_eve_argus_settings_from_context(ctx)
    asyncio.run(
        _fetch_market_history(
            settings=settings, region_id=region_id, type_id=type_id, quiet=quiet
        )
    )


async def _fetch_market_history(
    *, settings: EveArgusSettings, region_id: int, type_id: int, quiet: bool
) -> None:
    """Update a single pair and report freshness or failure."""
    messenger = Console(stderr=True, quiet=quiet)
    messenger.print(
        f"Checking market history for region {region_id}, type {type_id}..."
    )
    async with EveArgusResources(settings) as resources:
        result = await update_market_history(
            resources.esi_link,
            resources.esi_schema,
            resources.market_history_db_connection,
            region_id=region_id,
            type_id=type_id,
        )
        report_update_result(
            result,
            messenger=Console(stderr=True)
            if result.status is UpdateStatus.FAILED
            else messenger,
            dataset_name=f"market history for region {region_id}, type {type_id}",
        )
