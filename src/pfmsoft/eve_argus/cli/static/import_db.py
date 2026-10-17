"""Import static datasets from an eve-sd source."""

from pathlib import Path
from typing import Annotated

import typer
from pfmsoft.eve_sd import EveSdDbQueryManager
from rich.console import Console

from pfmsoft.eve_argus.cli.helpers import get_eve_argus_settings_from_context
from pfmsoft.eve_argus.helpers.connection_helpers import db_connection_manager
from pfmsoft.eve_argus.static import read
from pfmsoft.eve_argus.static.create import create_db
from pfmsoft.eve_argus.static.store import StaticStore

app = typer.Typer(
    no_args_is_help=True,
)


@app.command(name="import-db")
def import_db(
    ctx: typer.Context,
    file_in: Annotated[
        Path,
        typer.Option(
            "--from",
            file_okay=True,
            dir_okay=False,
            help="Path to eve-sd sqlite database.",
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
):
    """Import static datasets from an eve-sd sqlite database."""
    if quiet:
        messenger = Console(stderr=True, quiet=True)
    else:
        messenger = Console(stderr=True)
    settings = get_eve_argus_settings_from_context(ctx)
    eve_sd_db_query_manager = EveSdDbQueryManager(file_in)

    static_store = StaticStore(settings.static_database_store)
    with eve_sd_db_query_manager as esd_db:
        sde_metadata = esd_db.query.sde_metadata
        static_store.add_entry(
            build_number=sde_metadata.buildNumber, release_date=sde_metadata.releaseDate
        )
        db_path = static_store.get_file_path_for_entry(sde_metadata.buildNumber)
        with db_connection_manager(db_path=db_path) as connection:
            try:
                create_db(argus_connection=connection, query_manager=esd_db)
                _ = read.sde_metadata(connection)
            except Exception as e:
                messenger.print(
                    f"[red]There was an error importing the static datasets. {e}[/red]"
                )
                raise typer.Exit(code=1) from e
