"""Export the configured static market-group dataset without refreshing it."""

import csv
import json
import logging
import sqlite3
from dataclasses import asdict, fields
from io import StringIO
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from pfmsoft.eve_argus.cli.helpers import (
    get_eve_argus_settings_from_context,
    get_static_database_path,
)
from pfmsoft.eve_argus.helpers.connection_helpers import db_connection_manager
from pfmsoft.eve_argus.settings import EveArgusSettings
from pfmsoft.eve_argus.static import read as static_read
from pfmsoft.eve_argus.static.models import MarketGroupsRecord

logger = logging.getLogger(__name__)
app = typer.Typer(no_args_is_help=True)


@app.command(name="market-groups")
def market_groups(
    ctx: typer.Context,
    to: Annotated[
        Path, typer.Option("--to", help="Directory for market-group JSON and CSV.")
    ],
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace existing export files.")
    ] = False,
    quiet: Annotated[
        bool, typer.Option("--quiet", help="Suppress success messages, not errors.")
    ] = False,
) -> None:
    """Export all market groups from the configured Argus static database, offline."""
    settings = get_eve_argus_settings_from_context(ctx)
    try:
        _export_market_groups(
            settings=settings,
            destination=to,
            overwrite=overwrite,
            messenger=Console(stderr=True, quiet=quiet),
        )
    except (OSError, sqlite3.Error, ValueError) as error:
        logger.error("Market-group export failed: %s", error)
        Console(stderr=True).print(f"Error: {error}", markup=False)
        raise typer.Exit(code=1) from error


def _export_market_groups(
    *,
    settings: EveArgusSettings,
    destination: Path,
    overwrite: bool,
    messenger: Console,
) -> None:
    """Read and render the whole dataset before writing either output file."""
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"Export destination is not a directory: {destination}")
    paths = [destination / f"market-groups.{suffix}" for suffix in ("json", "csv")]
    for path in paths:
        if path.exists() and (not overwrite or not path.is_file()):
            raise ValueError(
                f"Export path already exists: {path}. "
                "Use --overwrite to replace existing files."
            )
    with db_connection_manager(
        get_static_database_path(settings), read_only=True
    ) as connection:
        dataset = static_read.market_groups(connection)
    records = {key: asdict(dataset[key]) for key in sorted(dataset)}
    json_content = json.dumps(records, indent=2, ensure_ascii=False) + "\n"
    csv_stream = StringIO(newline="")
    writer = csv.DictWriter(
        csv_stream,
        fieldnames=[field.name for field in fields(MarketGroupsRecord)],
        lineterminator="\n",
    )
    writer.writeheader()
    for market_group_id in sorted(
        records, key=lambda group_id: dataset[group_id].str_path_str()
    ):
        record = records[market_group_id]
        writer.writerow(
            {
                **{
                    key: json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (tuple, list, dict))
                    else value
                    for key, value in record.items()
                },
                "str_path": dataset[market_group_id].str_path_str(),
            }
        )
    destination.mkdir(parents=True, exist_ok=True)
    for path, content in zip(paths, (json_content, csv_stream.getvalue()), strict=True):
        with path.open(
            "w" if overwrite else "x", encoding="utf-8", newline=""
        ) as stream:
            stream.write(content)
        messenger.print(f"Wrote {path}", markup=False)
