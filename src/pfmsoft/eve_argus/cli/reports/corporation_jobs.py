"""Generate corporation industry job reports from the latest stored snapshot."""

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
from pfmsoft.eve_argus.reports.corp_industry_jobs import collect_corporation_jobs_report
from pfmsoft.eve_argus.reports.corp_industry_jobs_render import (
    render_corporation_jobs_csv,
    render_corporation_jobs_json,
    render_corporation_jobs_markdown,
)
from pfmsoft.eve_argus.settings import EveArgusSettings
from pfmsoft.eve_argus.static import read as static_read

logger = logging.getLogger(__name__)
app = typer.Typer(no_args_is_help=True)


@app.command(name="corporation-jobs")
def corporation_jobs(
    ctx: typer.Context,
    to: Annotated[
        Path,
        typer.Option("--to", help="Directory for the JSON, CSV, and Markdown reports."),
    ],
    corporation_id: Annotated[
        int | None,
        typer.Option(
            "--corporation-id",
            min=1,
            help="Corporation ID, or the configured default when omitted.",
        ),
    ] = None,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace existing report files.")
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Suppress progress, but not errors or warnings."),
    ] = False,
) -> None:
    """Report stored corporation jobs without refreshing the source snapshot."""
    settings = get_eve_argus_settings_from_context(ctx)
    resolved_id = settings.corporation_id if corporation_id is None else corporation_id
    if resolved_id is None or resolved_id <= 0:
        raise typer.BadParameter(
            "Provide --corporation-id or configure default_ids.corporation_id."
        )
    messenger = Console(stderr=True, quiet=quiet)
    warnings = Console(stderr=True)
    try:
        asyncio.run(
            _generate_reports(
                settings=settings,
                corporation_id=resolved_id,
                destination=to,
                overwrite=overwrite,
                messenger=messenger,
                warnings=warnings,
            )
        )
    except (OSError, sqlite3.Error, ValueError, RuntimeError, TemplateError) as error:
        logger.error("Corporation jobs report failed: %s", error)
        warnings.print(f"Error: {error}", markup=False)
        raise typer.Exit(code=1) from error


async def _generate_reports(
    *,
    settings: EveArgusSettings,
    corporation_id: int,
    destination: Path,
    overwrite: bool,
    messenger: Console,
    warnings: Console,
) -> None:
    """Load the latest scoped snapshot, collect once, and write all three formats."""
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"Report destination is not a directory: {destination}")
    async with EveArgusResources(settings) as resources:
        responses = dynamic_read.corporation_industry_jobs_responses(
            resources.argus_dynamic_db_connection,
            corporation_id=corporation_id,
        )
        if not responses:
            raise ValueError(
                f"No stored jobs snapshot for corporation {corporation_id}. Run "
                f"'eve-argus fetch corporation-jobs --corporation-id {corporation_id}' first."
            )
        latest = responses[0]
        stem = (
            f"corporation-jobs-{corporation_id}-{file_safe_string(latest.received_at)}"
        )
        paths = tuple(
            destination / f"{stem}.{extension}" for extension in ("json", "csv", "md")
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
        jobs = dynamic_read.corporation_industry_jobs(
            resources.argus_dynamic_db_connection,
            response_metadata_id=latest.response_metadata_id,
        )
        report = await collect_corporation_jobs_report(
            jobs=jobs,
            types=static_read.types(
                resources.argus_static_db_connection, only_published=False
            ),
            market_groups=static_read.market_groups(
                resources.argus_static_db_connection
            ),
            industry_activities=static_read.industry_activities(
                resources.argus_static_db_connection
            ),
            esi_link=resources.esi_link,
            schema=resources.esi_schema,
            generated_at=Instant.now(),
        )
    if report.is_stale:
        warnings.print(
            "Warning: the stored jobs snapshot has expired; it was not refreshed."
        )
    outputs = (
        render_corporation_jobs_json(report),
        render_corporation_jobs_csv(report),
        render_corporation_jobs_markdown(report),
    )
    destination.mkdir(parents=True, exist_ok=True)
    for path, content in zip(paths, outputs, strict=True):
        with path.open(
            "w" if overwrite else "x", encoding="utf-8", newline=""
        ) as stream:
            stream.write(content)
    for path in paths:
        messenger.print(f"Wrote {path}", markup=False)
