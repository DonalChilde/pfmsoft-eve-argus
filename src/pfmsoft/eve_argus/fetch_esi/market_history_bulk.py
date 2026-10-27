"""Bounded concurrent market-history updates with a global failure limit."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from itertools import product
from sqlite3 import Connection

from pfmsoft.eve_link import EsiLink, EsiSchema

from pfmsoft.eve_argus.fetch_esi.market_history import (
    MarketHistoryUpdateResult,
    update_market_history,
)
from pfmsoft.eve_argus.fetch_esi.update import UpdateResult, UpdateStatus

logger = logging.getLogger(__name__)

MARKET_HISTORY_WORKER_COUNT = 50
MARKET_HISTORY_FAILURE_LIMIT = 50

type ResultReporter = Callable[[int, int, MarketHistoryUpdateResult], None]


@dataclass(slots=True, kw_only=True)
class MarketHistoryBulkResult:
    """Run totals, including interrupted pairs and pairs never started.

    Successful writes remain committed even when the run aborts. Failure totals
    may exceed the limit if an in-flight update finishes while being cancelled.
    """

    total: int
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    cancelled: int = 0
    aborted: bool = False

    @property
    def completed(self) -> int:
        """Number of pairs with an update outcome."""
        return self.updated + self.skipped + self.failed

    @property
    def not_started(self) -> int:
        """Number of pairs never started by a worker."""
        return self.total - self.completed - self.cancelled


async def update_market_histories(
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: Connection,
    *,
    region_ids: set[int],
    type_ids: set[int],
    on_result: ResultReporter | None = None,
    worker_count: int = MARKET_HISTORY_WORKER_COUNT,
    failure_limit: int = MARKET_HISTORY_FAILURE_LIMIT,
    stale_after_days: int | None = None,
) -> MarketHistoryBulkResult:
    """Update unique region/type pairs using a bounded pool of async workers.

    Args:
        esi_link: Shared ESI client, including its caching and rate limiting.
        schema: ESI request schema.
        connection: History connection used only on the event-loop thread.
        region_ids: Validated region IDs.
        type_ids: Selected market type IDs.
        on_result: Optional synchronous reporter called for each completed pair.
        worker_count: Maximum number of pairs to process concurrently.
        failure_limit: Maximum number of failed pairs before aborting.
        stale_after_days: Additional received-age gate in 24-hour days.
            None or zero disables it; existing expiry checks still apply.

    Returns:
        Totals after all pairs finish or the global failure limit is reached.
        On abort, pending tasks are cancelled and awaited before returning.
        Unexpired responses are skipped even when they contain no history.

    Raises:
        ValueError: If worker_count or failure_limit is not positive, or
            stale_after_days is negative.

    Ordinary updater exceptions are logged and counted as failed pairs. External
    cancellation propagates after child cleanup and is not an update failure.
    """
    if worker_count <= 0:
        raise ValueError("worker_count must be positive")
    if failure_limit <= 0:
        raise ValueError("failure_limit must be positive")
    if stale_after_days is not None and stale_after_days < 0:
        raise ValueError("stale_after_days must be nonnegative")
    update_history = update_market_history
    if stale_after_days is not None:
        update_history = partial(
            update_market_history, stale_after_days=stale_after_days
        )
    summary = MarketHistoryBulkResult(total=len(region_ids) * len(type_ids))
    pairs = product(sorted(region_ids), sorted(type_ids))
    tasks: list[asyncio.Task[None]] = []

    async def update_pair(region_id: int, type_id: int) -> None:
        result: MarketHistoryUpdateResult
        try:
            result = await update_history(
                esi_link, schema, connection, region_id=region_id, type_id=type_id
            )
        except asyncio.CancelledError:
            summary.cancelled += 1
            raise
        except Exception as error:
            logger.exception(
                "Market-history update raised for region %s, type %s",
                region_id,
                type_id,
            )
            result = UpdateResult(
                status=UpdateStatus.FAILED,
                previous_state=None,
                failure_message=f"{type(error).__name__}: {error}",
            )

        match result.status:
            case UpdateStatus.UPDATED:
                summary.updated += 1
            case UpdateStatus.SKIPPED:
                summary.skipped += 1
            case UpdateStatus.FAILED:
                summary.failed += 1

        if summary.failed >= failure_limit and not summary.aborted:
            summary.aborted = True
            current = asyncio.current_task()
            for task in tasks:
                if task is not current and not task.done():
                    task.cancel()
        if on_result is not None:
            on_result(region_id, type_id, result)

    async def worker() -> None:
        """Claim another pair after each outcome until exhausted or aborted."""
        while not summary.aborted:
            pair = next(pairs, None)
            if pair is None:
                return
            region_id, type_id = pair
            await update_pair(region_id, type_id)
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                return

    async with asyncio.TaskGroup() as group:
        tasks = [
            group.create_task(worker()) for _ in range(min(worker_count, summary.total))
        ]
    return summary
