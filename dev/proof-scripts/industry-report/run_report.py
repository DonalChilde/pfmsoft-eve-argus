"""Run the isolated industry proof with synthetic or explicit stored inputs."""

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

from industry_proof import build_report
from proof_inputs import DatabasePaths, demo_inputs, read_inputs
from proof_render import write_reports

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Generate CSV/Markdown/HTML without touching application code or sources."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demo", action="store_true", help="Use fictional synthetic inputs."
    )
    parser.add_argument("--static-database", type=Path)
    parser.add_argument("--dynamic-database", type=Path)
    parser.add_argument("--history-database", type=Path)
    parser.add_argument("--corporation-id", type=int)
    parser.add_argument(
        "--type-id",
        type=int,
        action="append",
        default=[],
        help="Product type ID; repeat. Otherwise select a bounded sample.",
    )
    parser.add_argument("--to", type=Path, required=True, help="Output directory.")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    paths = (args.static_database, args.dynamic_database, args.history_database)
    if args.demo and (any(paths) or args.corporation_id is not None):
        parser.error(
            "--demo cannot be combined with database or corporation arguments."
        )
    if not args.demo and (not all(paths) or args.corporation_id is None):
        parser.error(
            "Use --demo, or provide all three database paths and --corporation-id."
        )
    try:
        if args.demo:
            data = demo_inputs()
            selected = tuple(args.type_id) or (100, 200, 300)
        else:
            if args.corporation_id is None:
                raise ValueError("Corporation ID is required for stored inputs.")
            data, selected = read_inputs(
                DatabasePaths(static=paths[0], dynamic=paths[1], history=paths[2]),
                corporation_id=args.corporation_id,
                product_ids=tuple(args.type_id),
            )
        report = build_report(data, product_ids=selected)
        for warning in data.warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        for source in data.sources:
            if source.freshness(now=report.generated_at) == "stale":
                print(
                    f"Warning: stale source: {source.label}, {source.received_at}",
                    file=sys.stderr,
                )
        for plan in report.plans:
            for warning in plan.warnings:
                print(
                    f"Warning [{plan.type_id}/{plan.strategy}]: {warning}",
                    file=sys.stderr,
                )
        for path in write_reports(
            report, destination=args.to, overwrite=args.overwrite
        ):
            print(f"Wrote {path}", file=sys.stderr)
        incomplete = sum(p.status == "incomplete" for p in report.plans)
        print(
            f"{len(report.plans)} estimates; {incomplete} incomplete.", file=sys.stderr
        )
        return 0
    except (OSError, sqlite3.Error, ValueError) as error:
        logger.error("Industry proof failed: %s", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
