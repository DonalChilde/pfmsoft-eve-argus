"""Run the isolated industry proof with synthetic or explicit stored inputs."""

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

from industry_proof import Planner, build_report
from proof_inputs import (
    DatabasePaths,
    demo_inputs,
    read_inputs,
    select_bpo_products,
    select_sample,
)
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
    parser.add_argument(
        "--history-stale",
        type=int,
        default=7,
        help="History receipt age in days before stale (default: 7; nonnegative).",
    )
    parser.add_argument("--corporation-id", type=int, help="Stored corporation scope.")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--owned",
        action="store_true",
        help="All owned published BPO products and their invention products.",
    )
    selection.add_argument(
        "--not-owned",
        action="store_true",
        help="All unowned published BPO products and their invention products.",
    )
    selection.add_argument(
        "--sample", action="store_true", help="Select a bounded sample (default)."
    )
    selection.add_argument(
        "--type-id",
        type=int,
        action="append",
        default=[],
        help="Product type ID; repeat. Does not expand invention products.",
    )
    parser.add_argument(
        "--me", type=int, default=10, help="Unowned BPO ME, 0-10 (default: 10)."
    )
    parser.add_argument(
        "--te", type=int, default=20, help="Unowned BPO TE, 0-20 (default: 20)."
    )
    parser.add_argument("--to", type=Path, required=True, help="Output directory.")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if args.history_stale < 0:
        parser.error("--history-stale must be nonnegative.")
    if args.corporation_id is not None and args.corporation_id < 1:
        parser.error("--corporation-id must be positive.")
    if any(t < 1 for t in args.type_id):
        parser.error("--type-id must be positive.")
    if not 0 <= args.me <= 10 or not 0 <= args.te <= 20:
        parser.error("--me must be 0-10 and --te must be 0-20.")
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
            if args.owned or args.not_owned:
                selected = select_bpo_products(
                    data,
                    published_blueprint_ids=set(data.blueprints),
                    owned=args.owned,
                    me=args.me,
                    te=args.te,
                )
            elif args.type_id:
                selected = tuple(args.type_id)
            else:
                selected = select_sample(data)
        else:
            if args.corporation_id is None:
                raise ValueError("Corporation ID is required for stored inputs.")
            data, selected = read_inputs(
                DatabasePaths(static=paths[0], dynamic=paths[1], history=paths[2]),
                corporation_id=args.corporation_id,
                product_ids=tuple(args.type_id),
                selection="owned"
                if args.owned
                else "not-owned"
                if args.not_owned
                else "sample",
                me=args.me,
                te=args.te,
                history_stale_days=args.history_stale,
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
        planner = Planner(data)
        for plan in report.plans:
            for warning in plan.warnings:
                print(
                    f"Warning [{planner.identity(plan.type_id)}/{plan.strategy}]: {warning}",
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
