"""Shared setup and proof-only worker pool for cold-cache history benchmarks."""

import argparse
import asyncio
import json
import logging
import os
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from sqlite3 import Connection
from time import perf_counter
from typing import Literal

from pfmsoft.eve_link import EsiLink, EsiSchema, SimpleRequests
from pydantic_settings import SettingsConfigDict

from pfmsoft.eve_argus.fetch_esi.market_history import (
    MarketHistoryUpdateResult,
    update_market_history,
)
from pfmsoft.eve_argus.fetch_esi.market_history_bulk import (
    MARKET_HISTORY_BATCH_SIZE,
    MARKET_HISTORY_FAILURE_LIMIT,
    MarketHistoryBulkResult,
    update_market_histories,
)
from pfmsoft.eve_argus.fetch_esi.update import UpdateResult, UpdateStatus
from pfmsoft.eve_argus.helpers.connection_helpers import (
    create_read_only_connection,
    create_read_write_connection,
)
from pfmsoft.eve_argus.helpers.market_groups import filter_type_ids_by_market_path
from pfmsoft.eve_argus.market_history.util import load_table_definitions
from pfmsoft.eve_argus.settings import (
    ENV_PREFIX,
    EveArgusSettingsPydantic,
    get_settings,
)
from pfmsoft.eve_argus.static import read
from pfmsoft.eve_argus.static.store import StaticStore

ROOT = Path(__file__).resolve().parents[3]
REGION_ID = 10000002
type Reporter = Callable[[int, int, MarketHistoryUpdateResult], None]
logger = logging.getLogger(__name__)


def positive_int(value: str) -> int:
    """Parse strictly positive benchmark sizes."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def application_directory(env_file: Path) -> Path:
    """Load the explicit benchmark env file, rejecting warm or unsafe targets."""
    if os.environ.get(f"{ENV_PREFIX}APPLICATION_DIRECTORY"):
        raise ValueError(
            f"Unset {ENV_PREFIX}APPLICATION_DIRECTORY so the benchmark env file wins."
        )
    if not env_file.is_file():
        raise FileNotFoundError(env_file)

    class BenchmarkEnvironment(EveArgusSettingsPydantic):
        model_config = SettingsConfigDict(
            env_file=env_file, env_prefix=ENV_PREFIX, env_file_encoding="utf-8"
        )

    configured = BenchmarkEnvironment().application_directory
    directory = (ROOT / configured).resolve()
    if not directory.is_relative_to(ROOT / "dev") or directory in (
        ROOT / "dev",
        ROOT / "dev/app-dir",
    ):
        raise ValueError("Benchmark application directory must be isolated under dev/.")
    if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
        raise ValueError(
            f"Refusing a warm application directory: {directory}. "
            "Use a fresh directory in your benchmark eve-argus.env.dev."
        )
    return directory


def select_types(static_db: Path, *, count: int) -> list[int]:
    """Select the same sorted published market types for either scheduling method."""
    with closing(create_read_only_connection(static_db)) as connection:
        if REGION_ID not in read.map_regions(connection):
            raise ValueError(f"Static database is missing region {REGION_ID}.")
        types = read.types(connection, only_published=True)
        market_ids = filter_type_ids_by_market_path(read.market_groups(connection))
        selected = sorted(market_ids & types.keys())
    if len(selected) < count:
        raise ValueError(f"Need {count} market types, but only {len(selected)} exist.")
    return selected[:count]


async def run_workers(
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: Connection,
    *,
    type_ids: list[int],
    concurrency: int,
    on_result: Reporter,
) -> MarketHistoryBulkResult:
    """Keep workers occupied without batch barriers; do not change production code.

    All database access remains on the event-loop thread. Stop at the same global
    failure limit as the batch runner and await active cancellations.
    """
    if concurrency <= 0:
        raise ValueError("concurrency must be positive")
    summary = MarketHistoryBulkResult(total=len(type_ids))
    remaining = iter(type_ids)
    tasks: list[asyncio.Task[None]] = []

    async def worker() -> None:
        for type_id in remaining:
            if summary.aborted:
                return
            result: MarketHistoryUpdateResult
            try:
                try:
                    result = await update_market_history(
                        esi_link,
                        schema,
                        connection,
                        region_id=REGION_ID,
                        type_id=type_id,
                    )
                except Exception as error:
                    logger.exception("Worker update raised for type %s", type_id)
                    result = UpdateResult(
                        status=UpdateStatus.FAILED,
                        previous_state=None,
                        failure_message=f"{type(error).__name__}: {error}",
                    )
            except asyncio.CancelledError:
                summary.cancelled += 1
                raise
            match result.status:
                case UpdateStatus.UPDATED:
                    summary.updated += 1
                case UpdateStatus.SKIPPED:
                    summary.skipped += 1
                case UpdateStatus.FAILED:
                    summary.failed += 1
            if summary.failed >= MARKET_HISTORY_FAILURE_LIMIT and not summary.aborted:
                summary.aborted = True
                current = asyncio.current_task()
                for task in tasks:
                    if task is not current and not task.done():
                        task.cancel()
            on_result(REGION_ID, type_id, result)

    async with asyncio.TaskGroup() as group:
        tasks = [
            group.create_task(worker()) for _ in range(min(concurrency, len(type_ids)))
        ]
    return summary


def run_benchmark(method: Literal["batch", "worker"]) -> None:
    """Run a timed live proof with isolated caches and save reproducible inputs."""
    parser = argparse.ArgumentParser(
        description=f"Cold-cache {method} history benchmark"
    )
    parser.add_argument("--count", type=positive_int, default=2000)
    parser.add_argument(
        "--concurrency", type=positive_int, default=MARKET_HISTORY_BATCH_SIZE
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=ROOT / f"dev/market-history-perf-{method}/eve-argus.env.dev",
    )
    parser.add_argument(
        "--static-db",
        type=Path,
        help="Read-only Argus static database; defaults to the latest dev/app-dir build.",
    )
    args = parser.parse_args()
    directory = application_directory(args.env_file.resolve())
    static_db = args.static_db
    if static_db is None:
        store_path = ROOT / "dev/app-dir/static-db-store"
        if not (store_path / "manifest.json").is_file():
            raise FileNotFoundError(
                f"Missing {store_path}/manifest.json; pass --static-db."
            )
        static_db = StaticStore(store_path).get_file_path_for_entry(build_number=None)
    static_db = static_db.resolve()
    type_ids = select_types(static_db, count=args.count)
    settings = get_settings(application_directory=directory)
    logging.basicConfig(
        filename=settings.logging_directory / "benchmark.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    print(f"Method: {method}; region: {REGION_ID}; types: {len(type_ids)}")
    print(f"Application directory: {directory}")
    print(f"Static database: {static_db}")
    print(
        f"Concurrency: {args.concurrency}; client rate: "
        f"{settings.eve_link_settings.max_rate}/"
        f"{settings.eve_link_settings.time_period}s"
    )
    (directory / "type-ids.json").write_text(json.dumps(type_ids), encoding="utf-8")
    overall_start = perf_counter()
    requests = SimpleRequests(settings=settings.eve_link_settings)
    schema = requests.get_schema(compatibility_date=settings.compatibility_date)

    async def benchmark() -> tuple[MarketHistoryBulkResult, float]:
        with closing(
            create_read_write_connection(
                settings.market_history_database, init_sql=load_table_definitions()
            )
        ) as connection:
            async with requests.esi_link_factory() as esi_link:
                completed = 0
                start = perf_counter()

                def report(
                    region_id: int, type_id: int, result: MarketHistoryUpdateResult
                ) -> None:
                    nonlocal completed
                    completed += 1
                    if result.status is UpdateStatus.FAILED:
                        print(f"FAILED {region_id}/{type_id}: {result.failure_message}")
                    if completed % 100 == 0:
                        elapsed = perf_counter() - start
                        print(
                            f"{completed}/{len(type_ids)} pairs in {elapsed:.2f}s",
                            flush=True,
                        )

                if method == "batch":
                    summary = await update_market_histories(
                        esi_link,
                        schema,
                        connection,
                        region_ids={REGION_ID},
                        type_ids=set(type_ids),
                        batch_size=args.concurrency,
                        failure_limit=MARKET_HISTORY_FAILURE_LIMIT,
                        on_result=report,
                    )
                else:
                    summary = await run_workers(
                        esi_link,
                        schema,
                        connection,
                        type_ids=type_ids,
                        concurrency=args.concurrency,
                        on_result=report,
                    )
                elapsed = perf_counter() - start
                return summary, elapsed

    summary, elapsed = asyncio.run(benchmark())
    result: dict[str, str | int | float | bool | list[int]] = {
        "method": method,
        "region_id": REGION_ID,
        "static_db": str(static_db),
        "application_directory": str(directory),
        "type_ids": type_ids,
        "concurrency": args.concurrency,
        "max_rate": settings.eve_link_settings.max_rate,
        "time_period": settings.eve_link_settings.time_period,
        "failure_limit": MARKET_HISTORY_FAILURE_LIMIT,
        "elapsed_seconds": elapsed,
        "setup_and_run_seconds": perf_counter() - overall_start,
        "completed_pairs_per_minute": summary.completed / elapsed * 60,
        "total": summary.total,
        "updated": summary.updated,
        "skipped": summary.skipped,
        "failed": summary.failed,
        "cancelled": summary.cancelled,
        "not_started": summary.not_started,
        "aborted": summary.aborted,
    }
    filename = directory / "benchmark-result.json"
    filename.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result | {"type_ids": "see type-ids.json"}, indent=2))
    print(f"Saved results to {filename}")
    if summary.failed or summary.cancelled or summary.not_started or summary.skipped:
        raise SystemExit("Incomplete or non-cold benchmark; inspect results and logs.")
