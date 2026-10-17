import asyncio
import sqlite3
from math import ceil
from typing import Annotated

import typer
from pfmsoft.eve_link import EsiLink, EsiSchema
from rich.console import Console
from whenever import Instant

from pfmsoft.eve_argus.cli.helpers import get_eve_argus_settings_from_context
from pfmsoft.eve_argus.dynamic import read, write
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.fetch_esi import update_corporation_jobs
from pfmsoft.eve_argus.fetch_esi.update import UpdateStatus
from pfmsoft.eve_argus.settings import EveArgusSettings

app = typer.Typer(no_args_is_help=True)


@app.command(name="corporation-jobs")
def fetch_corporation_jobs(
    ctx: typer.Context,
    corporation_id: Annotated[
        int,
        typer.Option(
            "--corporation-id",
            help="The ID of the corporation to fetch jobs for.",
            show_default=True,
        ),
    ],
    character_id: Annotated[
        int,
        typer.Option(
            "--character-id",
            help="The ID of the character performing the fetch.",
            show_default=True,
        ),
    ],
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            help="Suppress messages.",
            show_default=True,
        ),
    ] = False,
) -> None:
    """Fetch corporation blueprint data into the dynamic database."""
    settings = get_eve_argus_settings_from_context(ctx)
    if quiet:
        messenger = Console(stderr=True, quiet=True)
    else:
        messenger = Console(stderr=True)
