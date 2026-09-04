# uses jinja to generate markdown reports.
# use dataclasses over dicts to pass jinja context.

"""Render the corporation owned-vs-missing BPO report as Markdown."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.resources import files

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from whenever import Instant

from pfmsoft.eve_argus.reports.corp_missing_bpo import (
    CorpBpoReport,
    MissingBpoRow,
    OwnedBpoRow,
)


@dataclass(frozen=True, slots=True)
class OwnedPathGroup:
    """Owned blueprint rows sharing one market path."""

    market_path: str
    rows: list[OwnedBpoRow]


@dataclass(frozen=True, slots=True)
class MissingPathGroup:
    """Missing blueprint rows sharing one market path."""

    market_path: str
    rows: list[MissingBpoRow]


@dataclass(frozen=True, slots=True)
class CorpBpoReportContext:
    """Dataclass context supplied to the corporation BPO report templates."""

    report: CorpBpoReport
    generated_at: str
    owned_groups: list[OwnedPathGroup]
    missing_groups: list[MissingPathGroup]


def _group_by_market_path[RowT: OwnedBpoRow | MissingBpoRow](
    rows: Sequence[RowT],
) -> dict[str, list[RowT]]:
    """Group rows by market path, preserving each path's rows."""
    grouped: dict[str, list[RowT]] = defaultdict(list)
    for row in rows:
        grouped[row.market_path].append(row)
    return grouped


def _owned_groups(rows: Sequence[OwnedBpoRow]) -> list[OwnedPathGroup]:
    """Group owned rows by market path, sorted alphabetically by path."""
    grouped = _group_by_market_path(rows)
    return [
        OwnedPathGroup(market_path=path, rows=grouped[path]) for path in sorted(grouped)
    ]


def _missing_groups(rows: Sequence[MissingBpoRow]) -> list[MissingPathGroup]:
    """Group missing rows by market path, sorted alphabetically by path."""
    grouped = _group_by_market_path(rows)
    return [
        MissingPathGroup(market_path=path, rows=grouped[path])
        for path in sorted(grouped)
    ]


def render_corp_bpo_report_markdown(
    report: CorpBpoReport,
    *,
    report_generated_at: Instant | None = None,
) -> str:
    """Render the corporation owned-vs-missing BPO report as a Markdown report."""
    report_time = report_generated_at or Instant.now()
    context = CorpBpoReportContext(
        report=report,
        generated_at=report_time.format_iso(),
        owned_groups=_owned_groups(report.owned),
        missing_groups=_missing_groups(report.missing),
    )
    template_root = files("pfmsoft.eve_argus.templates") / "corp_missing_bpo"
    environment = Environment(
        loader=FileSystemLoader(str(template_root)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return environment.get_template("base.md.jinja2").render(context=context)


__all__ = ["render_corp_bpo_report_markdown"]
