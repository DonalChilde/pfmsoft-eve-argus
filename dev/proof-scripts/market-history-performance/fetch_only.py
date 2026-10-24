"""Time 500 direct market-history fetch calls without Argus history writes."""

import argparse
import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from _benchmark import REGION_ID, ROOT, application_directory, select_types
from pfmsoft.eve_link import EsiLink, EsiSchema, FailedEsiResponse, SimpleRequests

from pfmsoft.eve_argus.esi.fetch import market_history
from pfmsoft.eve_argus.settings import get_settings
from pfmsoft.eve_argus.static.store import StaticStore

CALL_COUNT = 500
logger = logging.getLogger(__name__)


@dataclass(slots=True, kw_only=True)
class FetchTiming:
    """Direct-call counts and elapsed time, including ESI client cache handling."""

    succeeded: int = 0
    failed: int = 0
    elapsed_seconds: float = 0.0


async def time_fetches(
    esi_link: EsiLink, schema: EsiSchema, *, type_ids: list[int]
) -> FetchTiming:
    """Schedule one direct call per type and wait for all results.

    Ordinary call exceptions are logged and counted so one failure does not
    cancel the remaining measurements. External cancellation still propagates.
    """
    timing = FetchTiming()

    async def fetch(type_id: int) -> None:
        try:
            response = await market_history(
                esi_link, schema, region_id=REGION_ID, type_id=type_id
            )
        except Exception:
            logger.exception("History fetch raised for type %s", type_id)
            timing.failed += 1
        else:
            if isinstance(response, FailedEsiResponse):
                logger.error(
                    "History fetch failed for type %s: %s",
                    type_id,
                    response.failed_response.error_messages,
                )
                timing.failed += 1
            else:
                timing.succeeded += 1

    start = perf_counter()
    async with asyncio.TaskGroup() as group:
        for type_id in type_ids:
            group.create_task(fetch(type_id))
    timing.elapsed_seconds = perf_counter() - start
    return timing


def main() -> None:
    """Load isolated settings, time exactly 500 fetches, and save the results."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=ROOT / "dev/market-history-perf-fetch/eve-argus.env.dev",
    )
    parser.add_argument(
        "--static-db",
        type=Path,
        help="Read-only Argus static database to select types.",
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
    type_ids = select_types(static_db, count=CALL_COUNT)
    settings = get_settings(application_directory=directory)
    logging.basicConfig(
        filename=settings.logging_directory / "fetch-only.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    print(f"Application directory: {directory}", flush=True)
    print(
        f"Fetching {CALL_COUNT} distinct types in region {REGION_ID} concurrently; "
        f"client rate {settings.eve_link_settings.max_rate}/"
        f"{settings.eve_link_settings.time_period}s",
        flush=True,
    )
    requests = SimpleRequests(settings=settings.eve_link_settings)
    schema = requests.get_schema(compatibility_date=settings.compatibility_date)

    async def run() -> FetchTiming:
        async with requests.esi_link_factory() as esi_link:
            return await time_fetches(esi_link, schema, type_ids=type_ids)

    timing = asyncio.run(run())
    result: dict[str, str | int | float] = {
        "succeeded": timing.succeeded,
        "failed": timing.failed,
        "elapsed_seconds": timing.elapsed_seconds,
        "region_id": REGION_ID,
        "call_count": CALL_COUNT,
        "static_db": str(static_db),
        "application_directory": str(directory),
        "max_rate": settings.eve_link_settings.max_rate,
        "time_period": settings.eve_link_settings.time_period,
        "completed_calls_per_minute": CALL_COUNT / timing.elapsed_seconds * 60,
    }
    (directory / "type-ids.json").write_text(json.dumps(type_ids), encoding="utf-8")
    filename = directory / "fetch-only-result.json"
    filename.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Saved results to {filename}; failure details: logs/fetch-only.log")
    if timing.failed:
        raise SystemExit(f"{timing.failed} of {CALL_COUNT} history calls failed.")


if __name__ == "__main__":
    main()
