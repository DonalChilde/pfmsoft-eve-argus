"""Eve Argus command line interface utilities."""

import typer
from pfmsoft.eve_auth_manager.cli import app as auth_manager_app
from pfmsoft.eve_link.cli import app as eve_link_app
from pfmsoft.eve_sd.cli import app as eve_sd_app

app = typer.Typer(
    no_args_is_help=True,
    help="Utilities for Eve Argus.",
)
app.add_typer(eve_link_app, name="eve-link")
app.add_typer(eve_sd_app, name="eve-sd")
app.add_typer(auth_manager_app, name="auth-manager")
