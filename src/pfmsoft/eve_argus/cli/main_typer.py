"""Main entry point for the Eve ESI Link CLI application."""

import logging
from dataclasses import asdict
from typing import Annotated

import typer
from pfmsoft.eve_link.settings import SETTINGS_KEY as EVE_LINK_SETTINGS_KEY
from pfmsoft.eve_sd.settings import SETTINGS_KEY as EVE_SD_SETTINGS_KEY
from rich.console import Console

from pfmsoft.eve_argus import __app_name__, __version__
from pfmsoft.eve_argus.cli import app as main_app
from pfmsoft.eve_argus.cli.helpers import get_eve_argus_settings_from_context
from pfmsoft.eve_argus.logging_config import (
    flush_deferred_handler,
    init_deferred_handler,
    setup_logging,
)
from pfmsoft.eve_argus.settings import SETTINGS_KEY, get_settings

logger = logging.getLogger(__name__)


def default_options(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the application version and exit",
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Initialize settings and logging for standalone CLI execution.

    Notes:
        The resolved EsiLinkSettings object is stored in ctx.obj under
        the eve-esi-link-settings key.
    """
    init_deferred_handler()
    settings = get_settings()

    setup_logging(log_dir=settings.logging_directory)
    flush_deferred_handler()
    ctx.obj = {
        SETTINGS_KEY: settings,
        EVE_LINK_SETTINGS_KEY: settings.eve_link_settings,
    }
    logger.info(
        f"Starting {__app_name__} v{__version__} with settings: {asdict(settings)!r}"
    )


app = typer.Typer(
    name="eve-link",
    help="A command line interface for interacting with EVE Online's ESI API.",
    callback=default_options,
    no_args_is_help=True,
)


@app.command()
def version(ctx: typer.Context) -> None:
    """Display the application version and exit."""
    settings = get_eve_argus_settings_from_context(ctx)
    console = Console(stderr=True)
    console.print(f"{__app_name__} v{__version__}")
    console.print(f"Settings:")
    console.print(settings)


app.add_typer(main_app)
