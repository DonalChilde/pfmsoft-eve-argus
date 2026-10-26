"""Pure JSON, two CSV, and packaged Jinja Markdown corporation blueprint renderers."""

import csv
from collections.abc import Iterable
from dataclasses import asdict, dataclass, fields
from io import StringIO

from jinja2 import Environment, PackageLoader, StrictUndefined
from pydantic import TypeAdapter

from pfmsoft.eve_argus.helpers.markdown import format_markdown, markdown_cell
from pfmsoft.eve_argus.reports.corp_blueprints import (
    CorporationBlueprintReportRow,
    CorporationBlueprintsReport,
    MissingBpoRow,
    OwnedBpoSummary,
)

_ADAPTER = TypeAdapter(CorporationBlueprintsReport)


@dataclass(slots=True, kw_only=True, frozen=True)
class BlueprintPathGroup[Row]:
    """Ordered rows sharing a market path; None is explicitly a nonmarket bucket."""

    market_path: tuple[str, ...] | None
    rows: tuple[Row, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class CorporationBlueprintsContext:
    """Typed context for summary, missing, original inventory and copy inventory."""

    report: CorporationBlueprintsReport
    owned: tuple[BlueprintPathGroup[OwnedBpoSummary], ...]
    missing: tuple[BlueprintPathGroup[MissingBpoRow], ...]
    originals: tuple[BlueprintPathGroup[CorporationBlueprintReportRow], ...]
    copies: tuple[BlueprintPathGroup[CorporationBlueprintReportRow], ...]


def _group_by_path[
    Row: CorporationBlueprintReportRow | OwnedBpoSummary | MissingBpoRow
](
    rows: Iterable[Row],
) -> tuple[BlueprintPathGroup[Row], ...]:
    grouped: dict[tuple[str, ...] | None, list[Row]] = {}
    for row in rows:
        grouped.setdefault(row.market_path, []).append(row)
    return tuple(
        BlueprintPathGroup(market_path=path, rows=tuple(grouped[path]))
        for path in sorted(grouped, key=lambda path: (path is None, path or ()))
    )


def build_markdown_context(
    report: CorporationBlueprintsReport,
) -> CorporationBlueprintsContext:
    """Group each view without modifying source ordering or collecting new data."""
    return CorporationBlueprintsContext(
        report=report,
        owned=_group_by_path(report.owned_bpos),
        missing=_group_by_path(report.missing_bpos),
        originals=_group_by_path(
            row for row in report.inventory if row.blueprint_kind != "copy"
        ),
        copies=_group_by_path(
            row for row in report.inventory if row.blueprint_kind == "copy"
        ),
    )


def render_corporation_blueprints_json(report: CorporationBlueprintsReport) -> str:
    """Serialize all views and metadata, retaining raw sentinels and nullable fields."""
    return _ADAPTER.dump_json(report, indent=2).decode("utf-8") + "\n"


def _render_csv(
    report: CorporationBlueprintsReport,
    *,
    rows: Iterable[CorporationBlueprintReportRow | MissingBpoRow],
    row_type: type[CorporationBlueprintReportRow] | type[MissingBpoRow],
) -> str:
    metadata: dict[str, object] = {
        "corporation_id": report.corporation_id,
        "corporation_name": report.corporation_name,
        "response_metadata_id": report.response_metadata_id,
        "received_at": report.received_at,
        "expires_at": report.expires_at,
        "argus_expires_at": report.argus_expires_at,
        "generated_at": report.generated_at,
        "is_stale": report.is_stale,
    }
    columns = [
        *metadata,
        *(field.name for field in fields(row_type) if field.name not in metadata),
    ]
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        values = asdict(row)
        values["market_path"] = (
            "/".join(row.market_path) if row.market_path is not None else None
        )
        writer.writerow(metadata | values)
    return stream.getvalue()


def render_owned_blueprints_csv(report: CorporationBlueprintsReport) -> str:
    """Render one row per owned original/stack/copy with all raw fields and metadata."""
    return _render_csv(
        report, rows=report.inventory, row_type=CorporationBlueprintReportRow
    )


def render_missing_bpo_csv(report: CorporationBlueprintsReport) -> str:
    """Render missing eligible originals, empty optional cells, and fixed headers."""
    return _render_csv(report, rows=report.missing_bpos, row_type=MissingBpoRow)


def render_corporation_blueprints_markdown(report: CorporationBlueprintsReport) -> str:
    """Render all four views without clock, network, database, or file-writing access."""
    environment = Environment(
        loader=PackageLoader("pfmsoft.eve_argus.templates", "corp_blueprints"),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    rendered = environment.get_template(
        "report.md.jinja2", globals={"cell": markdown_cell}
    ).render(
        context=build_markdown_context(report),
    )
    return format_markdown(rendered)
