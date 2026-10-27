"""Compare whole-snapshot and per-type market-order summary calculation timings."""

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import TypedDict

from pfmsoft.eve_argus.dynamic import models, order_summary, read

ROOT = Path(__file__).resolve().parents[2]
SummaryRecords = dict[int, models.BuySellSummary]


@dataclass(frozen=True, slots=True, kw_only=True)
class Options:
    """Inputs shared by both timing paths."""

    response_metadata_id: int
    repeats: int = 3
    system_id: int | None = None
    location_id: int | None = None
    filter_factor: Decimal = order_summary.FILTER_FACTOR_DEFAULT
    limit_types: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Timing:
    """Elapsed stages; calculation includes constructing the result mapping."""

    setup_seconds: float
    calculation_seconds: float

    def as_dict(self) -> dict[str, float]:
        """Include total elapsed time alongside the two contiguous stages."""
        return {
            **asdict(self),
            "total_seconds": self.setup_seconds + self.calculation_seconds,
        }


class Comparison(TypedDict):
    """JSON-compatible timings and the workload needed to interpret them."""

    options: dict[str, int | str | None]
    snapshot_order_count: int
    available_type_count: int
    type_count: int
    selected_type_ids: list[int]
    sampled: bool
    on_demand_calls_per_run: int
    verified_equal: bool
    execution_orders: list[list[str]]
    runs: dict[str, list[dict[str, float]]]
    medians: dict[str, dict[str, float]]
    on_demand_total_ratio: float
    on_demand_extra_seconds: float
    on_demand_seconds_per_call: float
    market_order_indexes: list[str]
    on_demand_query_plan: list[str]


def open_database(path: Path) -> sqlite3.Connection:
    """Open an existing database read-only, without invoking schema initialization."""
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def select_types(connection: sqlite3.Connection, *, options: Options) -> list[int]:
    """Discover sorted scoped types, optionally selecting a reproducible prefix."""
    return sorted(
        read.market_order_types(
            connection,
            options.response_metadata_id,
            system_id=options.system_id,
            location_id=options.location_id,
        )
    )[: options.limit_types]


def measure_dataset(
    connection: sqlite3.Connection, *, options: Options, type_ids: list[int]
) -> tuple[Timing, SummaryRecords]:
    """Time loading all orders, then calculating both sides for the selected types."""
    started = perf_counter()
    dataset = read.market_orders(connection, options.response_metadata_id)
    dataset = replace(
        dataset, records={type_id: dataset.records[type_id] for type_id in type_ids}
    )
    loaded = perf_counter()
    summaries = order_summary.calculate_dataset_summaries(
        dataset,
        system_id=options.system_id,
        location_id=options.location_id,
        filter_factor=options.filter_factor,
    )
    finished = perf_counter()
    return (
        Timing(
            setup_seconds=loaded - started,
            calculation_seconds=finished - loaded,
        ),
        summaries.records,
    )


def measure_on_demand(
    connection: sqlite3.Connection, *, options: Options
) -> tuple[Timing, SummaryRecords]:
    """Time type discovery, then one query/calculation for both sides per type."""
    started = perf_counter()
    type_ids = select_types(connection, options=options)
    selected = perf_counter()
    records: SummaryRecords = {}
    for completed, type_id in enumerate(type_ids, start=1):
        buy, sell = read.calculate_market_order_summary(
            connection,
            options.response_metadata_id,
            type_id=type_id,
            system_id=options.system_id,
            location_id=options.location_id,
            filter_factor=options.filter_factor,
        )
        records[type_id] = models.BuySellSummary(buy_summary=buy, sell_summary=sell)
        if completed % 250 == 0:
            print(
                f"  {completed}/{len(type_ids)} types, "
                f"{perf_counter() - selected:.2f} seconds calculating",
                file=sys.stderr,
                flush=True,
            )
    finished = perf_counter()
    return (
        Timing(
            setup_seconds=selected - started,
            calculation_seconds=finished - selected,
        ),
        records,
    )


def measure_filtered_dataset(
    connection: sqlite3.Connection, *, options: Options, type_ids: list[int]
) -> tuple[Timing, SummaryRecords]:
    """Read the scoped orders once, then calculate summaries from the flat tuple."""
    started = perf_counter()
    response = next(
        response
        for response in read.market_orders_responses(connection, region_id=None)
        if response.response_metadata_id == options.response_metadata_id
    )
    orders = read.market_orders_filtered(
        connection,
        options.response_metadata_id,
        system_id=options.system_id,
        location_id=options.location_id,
    )
    selected_types = set(type_ids)
    orders = tuple(order for order in orders if order.type_id in selected_types)
    loaded = perf_counter()
    summaries = order_summary.calculate_order_summaries(
        orders,
        response=response,
        system_id=options.system_id,
        location_id=options.location_id,
        filter_factor=options.filter_factor,
    )
    finished = perf_counter()
    return (
        Timing(
            setup_seconds=loaded - started,
            calculation_seconds=finished - loaded,
        ),
        summaries.records,
    )


def benchmark(connection: sqlite3.Connection, *, options: Options) -> Comparison:
    """Run alternating comparisons and fail if either path produces different values."""
    if options.repeats < 1:
        raise ValueError("repeats must be positive.")
    if options.limit_types is not None and options.limit_types < 1:
        raise ValueError("limit_types must be positive.")
    if not options.filter_factor.is_finite():
        raise ValueError("filter_factor must be finite.")
    order_summary.validate_summary_options(
        system_id=options.system_id,
        location_id=options.location_id,
        filter_factor=options.filter_factor,
    )
    order_count = read.market_order_count(
        connection, response_metadata_id=options.response_metadata_id
    )
    available_types = select_types(
        connection, options=replace(options, limit_types=None)
    )
    type_ids = available_types[: options.limit_types]
    if not type_ids:
        raise ValueError("No order types match the selected response and scope.")

    runs: dict[str, list[dict[str, float]]] = {
        "dataset": [],
        "on_demand": [],
        "filtered_dataset": [],
    }
    execution_orders: list[list[str]] = []
    for repetition in range(options.repeats):
        methods = ["dataset", "on_demand", "filtered_dataset"]
        if repetition % 2:
            methods.reverse()
        execution_orders.append(methods)
        results: dict[str, SummaryRecords] = {}
        for method in methods:
            print(
                f"Run {repetition + 1}/{options.repeats}: {method}, "
                f"{len(type_ids)} types",
                file=sys.stderr,
                flush=True,
            )
            if method == "dataset":
                timing, records = measure_dataset(
                    connection, options=options, type_ids=type_ids
                )
            elif method == "on_demand":
                timing, records = measure_on_demand(connection, options=options)
            else:
                timing, records = measure_filtered_dataset(
                    connection, options=options, type_ids=type_ids
                )
            runs[method].append(timing.as_dict())
            results[method] = records
            print(
                f"  {timing.as_dict()['total_seconds']:.6f} seconds",
                file=sys.stderr,
                flush=True,
            )
        if any(records != results["dataset"] for records in results.values()):
            raise ValueError("Summary mismatch between dataset and on-demand results.")

    medians = {
        method: {
            stage: median(run[stage] for run in measurements)
            for stage in ("setup_seconds", "calculation_seconds", "total_seconds")
        }
        for method, measurements in runs.items()
    }
    dataset_total = medians["dataset"]["total_seconds"]
    demand_total = medians["on_demand"]["total_seconds"]
    if dataset_total <= 0:
        raise ValueError("Dataset timing is too short to calculate a timing ratio.")
    conditions = ["response_metadata_id = ?", "type_id = ?"]
    parameters = [options.response_metadata_id, type_ids[0]]
    for column, value in (
        ("system_id", options.system_id),
        ("location_id", options.location_id),
    ):
        if value is not None:
            conditions.append(f"{column} = ?")
            parameters.append(value)
    return Comparison(
        options={
            "response_metadata_id": options.response_metadata_id,
            "repeats": options.repeats,
            "system_id": options.system_id,
            "location_id": options.location_id,
            "filter_factor": str(options.filter_factor),
            "limit_types": options.limit_types,
        },
        snapshot_order_count=order_count,
        available_type_count=len(available_types),
        type_count=len(type_ids),
        selected_type_ids=type_ids,
        sampled=len(type_ids) < len(available_types),
        on_demand_calls_per_run=len(type_ids),
        verified_equal=True,
        execution_orders=execution_orders,
        runs=runs,
        medians=medians,
        on_demand_total_ratio=demand_total / dataset_total,
        on_demand_extra_seconds=demand_total - dataset_total,
        on_demand_seconds_per_call=(
            medians["on_demand"]["calculation_seconds"] / len(type_ids)
        ),
        market_order_indexes=[
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'index' AND tbl_name = 'market_orders' ORDER BY name"
            )
        ],
        on_demand_query_plan=[
            row[3]
            for row in connection.execute(
                f"EXPLAIN QUERY PLAN SELECT * FROM market_orders "
                f"WHERE {' AND '.join(conditions)} ORDER BY type_id, order_id",
                parameters,
            )
        ],
    )


def main() -> None:
    """Compare an existing snapshot without fetching data or writing application state."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=ROOT / "dev/app-dir/argus-dynamic-db.sqlite",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--response-metadata-id", type=int)
    source.add_argument("--region-id", type=int)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--system-id", type=int)
    scope.add_argument("--location-id", type=int)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--limit-types",
        type=int,
        help="Smoke run: first N sorted scoped types; still loads the whole snapshot.",
    )
    parser.add_argument(
        "--filter-factor", type=Decimal, default=order_summary.FILTER_FACTOR_DEFAULT
    )
    args = parser.parse_args()
    with closing(open_database(args.database)) as connection:
        connection.execute("BEGIN")
        responses = read.market_orders_responses(connection, region_id=args.region_id)
        response = next(
            (
                item
                for item in responses
                if args.response_metadata_id is None
                or item.response_metadata_id == args.response_metadata_id
            ),
            None,
        )
        if response is None:
            raise ValueError("No stored market-order response matches the selection.")
        print(
            f"Snapshot {response.response_metadata_id}, region {response.region_id}, "
            f"received {response.received_at}. No indexes will be added. "
            "Unindexed on-demand runs can be very slow.",
            file=sys.stderr,
            flush=True,
        )
        result = benchmark(
            connection,
            options=Options(
                response_metadata_id=response.response_metadata_id,
                repeats=args.repeats,
                system_id=args.system_id,
                location_id=args.location_id,
                filter_factor=args.filter_factor,
                limit_types=args.limit_types,
            ),
        )
    print(
        json.dumps(
            {
                "database": str(args.database.resolve()),
                "region_id": response.region_id,
                "received_at": response.received_at,
                **result,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
