"""Generate four corporation blueprint report files from one stored snapshot."""

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Annotated

import typer
from jinja2 import TemplateError
from rich.console import Console
from whenever import Instant

from pfmsoft.eve_argus.cli.helpers import get_eve_argus_settings_from_context
from pfmsoft.eve_argus.dynamic import read as dynamic_read
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.helpers.file_safe_string import file_safe_string
from pfmsoft.eve_argus.reports.corp_blueprints import (
    collect_corporation_blueprints_report,
)
from pfmsoft.eve_argus.reports.corp_blueprints_render import (
    render_corporation_blueprints_json,
    render_corporation_blueprints_markdown,
    render_missing_bpo_csv,
    render_owned_blueprints_csv,
)
from pfmsoft.eve_argus.settings import EveArgusSettings
from pfmsoft.eve_argus.static import read as static_read

logger = logging.getLogger(__name__)
app = typer.Typer(no_args_is_help=True)


@app.command(name="corporation-blueprints")
def corporation_blueprints(
    ctx: typer.Context,
    to: Annotated[
        Path,
        typer.Option(
            "--to", help="Directory for JSON, Markdown, owned CSV and missing-BPO CSV."
        ),
    ],
    corporation_id: Annotated[
        int | None,
        typer.Option(
            "--corporation-id", min=1, help="Corporation ID or configured default."
        ),
    ] = None,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace existing report files.")
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet", help="Suppress progress, but not errors or stale-data warnings."
        ),
    ] = False,
) -> None:
    """Report all owned blueprints and missing originals without refreshing inventory."""
    settings = get_eve_argus_settings_from_context(ctx)
    resolved_id = settings.corporation_id if corporation_id is None else corporation_id
    if resolved_id is None or resolved_id <= 0:
        raise typer.BadParameter(
            "Provide --corporation-id or configure default_ids.corporation_id."
        )
    errors = Console(stderr=True)
    try:
        asyncio.run(
            _generate_reports(
                settings=settings,
                corporation_id=resolved_id,
                destination=to,
                overwrite=overwrite,
                messenger=Console(stderr=True, quiet=quiet),
                errors=errors,
            )
        )
    except (OSError, sqlite3.Error, ValueError, RuntimeError, TemplateError) as error:
        logger.error("Corporation blueprints report failed: %s", error)
        errors.print(f"Error: {error}", markup=False)
        raise typer.Exit(code=1) from error


async def _generate_reports(
    *,
    settings: EveArgusSettings,
    corporation_id: int,
    destination: Path,
    overwrite: bool,
    messenger: Console,
    errors: Console,
) -> None:
    """Select a scoped snapshot, collect once, render all views, then write files."""
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"Report destination is not a directory: {destination}")
    async with EveArgusResources(settings) as resources:
        responses = dynamic_read.corporation_blueprints_responses(
            resources.argus_dynamic_db_connection,
            corporation_id=corporation_id,
        )
        if not responses:
            raise ValueError(
                f"No stored blueprints snapshot for corporation {corporation_id}. Run "
                "'eve-argus fetch corporation-blueprints "
                f"--corporation-id {corporation_id}' first."
            )
        latest = responses[0]
        stem = f"corporation-blueprints-{corporation_id}-{file_safe_string(latest.received_at)}"
        paths = tuple(
            destination / f"{stem}{suffix}"
            for suffix in (
                ".json",
                ".md",
                "-owned.csv",
                "-missing-bpo.csv",
            )
        )
        for path in paths:
            if path.exists() and (not overwrite or not path.is_file()):
                raise ValueError(
                    f"Report path already exists: {path}. "
                    "Use --overwrite to replace existing files."
                )
        messenger.print(
            f"Reading corporation {corporation_id} snapshot received {latest.received_at}..."
        )
        report = await collect_corporation_blueprints_report(
            blueprints=dynamic_read.corporation_blueprints(
                resources.argus_dynamic_db_connection,
                response_metadata_id=latest.response_metadata_id,
            ),
            types=static_read.types(
                resources.argus_static_db_connection, only_published=False
            ),
            market_groups=static_read.market_groups(
                resources.argus_static_db_connection
            ),
            esi_link=resources.esi_link,
            schema=resources.esi_schema,
            generated_at=Instant.now(),
        )
    if report.is_stale:
        errors.print(
            "Warning: the stored blueprints snapshot has expired; it was not refreshed."
        )
    outputs = (
        render_corporation_blueprints_json(report),
        render_corporation_blueprints_markdown(report),
        render_owned_blueprints_csv(report),
        render_missing_bpo_csv(report),
    )
    destination.mkdir(parents=True, exist_ok=True)
    for path, content in zip(paths, outputs, strict=True):
        with path.open(
            "w" if overwrite else "x", encoding="utf-8", newline=""
        ) as stream:
            stream.write(content)
    for path in paths:
        messenger.print(f"Wrote {path}", markup=False)
