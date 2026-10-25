"""Export static types as a CSV file without refreshing the database."""

import csv
import logging
import sqlite3
from dataclasses import asdict, fields
from io import StringIO
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from pfmsoft.eve_argus.cli.export._helpers import (
    check_destination,
    check_output_paths,
    export_file_name,
    write_outputs,
)
from pfmsoft.eve_argus.cli.helpers import (
    get_eve_argus_settings_from_context,
    get_static_database_path,
)
from pfmsoft.eve_argus.helpers.connection_helpers import db_connection_manager
from pfmsoft.eve_argus.settings import EveArgusSettings
from pfmsoft.eve_argus.static import read as static_read
from pfmsoft.eve_argus.static.models import (
    CategoriesDataset,
    GroupsDataset,
    MarketGroupsDataset,
    MetaGroupsDataset,
    TypesRecord,
)

logger = logging.getLogger(__name__)
app = typer.Typer(no_args_is_help=True)


@app.command(name="types")
def types(
    ctx: typer.Context,
    to: Annotated[
        Path, typer.Option("--to", help="Directory for the types CSV export.")
    ],
    include_unpublished: Annotated[
        bool,
        typer.Option(
            "--include-unpublished", help="Include unpublished types in the export."
        ),
    ] = False,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing export file.")
    ] = False,
    quiet: Annotated[
        bool, typer.Option("--quiet", help="Suppress success messages, not errors.")
    ] = False,
) -> None:
    """Export types from the configured Argus static database, offline."""
    settings = get_eve_argus_settings_from_context(ctx)
    try:
        _export_types(
            settings=settings,
            destination=to,
            include_unpublished=include_unpublished,
            overwrite=overwrite,
            messenger=Console(stderr=True, quiet=quiet),
        )
    except (OSError, sqlite3.Error, ValueError) as error:
        logger.error("Types export failed: %s", error)
        Console(stderr=True).print(f"Error: {error}", markup=False)
        raise typer.Exit(code=1) from error


def _export_types(
    *,
    settings: EveArgusSettings,
    destination: Path,
    include_unpublished: bool,
    overwrite: bool,
    messenger: Console,
) -> None:
    """Render all type rows before writing the CSV file."""
    check_destination(destination)
    with db_connection_manager(
        get_static_database_path(settings), read_only=True
    ) as connection:
        build_number = static_read.sde_metadata(connection).build_number
        dataset = static_read.types(connection, only_published=not include_unpublished)
        groups = static_read.groups(connection, only_published=False)
        categories = static_read.categories(connection, only_published=False)
        market_groups = static_read.market_groups(connection)
        meta_groups = static_read.meta_groups(connection)

    output_path = destination / export_file_name(
        stem="types", build_number=build_number, suffix="csv"
    )
    check_output_paths(paths=[output_path], overwrite=overwrite)
    csv_stream = StringIO(newline="")
    writer = csv.DictWriter(csv_stream, fieldnames=_fieldnames(), lineterminator="\n")
    writer.writeheader()
    for type_id in sorted(dataset):
        writer.writerow(
            _build_row(
                record=dataset[type_id],
                groups=groups,
                categories=categories,
                market_groups=market_groups,
                meta_groups=meta_groups,
            )
        )
    write_outputs(
        contents={output_path: csv_stream.getvalue()},
        overwrite=overwrite,
        messenger=messenger,
    )


def _fieldnames() -> list[str]:
    """Return type CSV columns, with linked names and description at the end."""
    result: list[str] = []
    for field in fields(TypesRecord):
        if field.name in {"description", "category_id"}:
            continue
        result.append(field.name)
        match field.name:
            case "group_id":
                result.extend(("group_name", "category_id", "category_name"))
            case "market_group_id":
                result.append("market_group_name")
            case "meta_group_id":
                result.append("meta_group_name")
    result.extend(("market_group_path", "description"))
    return result


def _build_row(
    *,
    record: TypesRecord,
    groups: GroupsDataset,
    categories: CategoriesDataset,
    market_groups: MarketGroupsDataset,
    meta_groups: MetaGroupsDataset,
) -> dict[str, object]:
    """Add names for a type's referenced group, category, and market metadata."""
    group = groups.get(record.group_id)
    category = categories.get(record.category_id)
    market_group = (
        market_groups.get(record.market_group_id)
        if record.market_group_id is not None
        else None
    )
    meta_group = (
        meta_groups.get(record.meta_group_id)
        if record.meta_group_id is not None
        else None
    )
    return {
        **asdict(record),
        "group_name": group.name if group is not None and group.name else "",
        "category_name": (
            category.name if category is not None and category.name else ""
        ),
        "market_group_name": (market_group.name if market_group is not None else ""),
        "meta_group_name": meta_group.name if meta_group is not None else "",
        "market_group_path": (
            market_group.str_path_str() if market_group is not None else ""
        ),
    }
