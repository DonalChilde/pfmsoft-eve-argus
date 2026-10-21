"""Bounded concurrent market-history updates with a global failure limit."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from itertools import batched, product
from sqlite3 import Connection

from pfmsoft.eve_link import EsiLink, EsiSchema

from pfmsoft.eve_argus.fetch_esi.market_history import (
    MarketHistoryUpdateResult,
    update_market_history,
)
from pfmsoft.eve_argus.fetch_esi.update import UpdateResult, UpdateStatus

logger = logging.getLogger(__name__)

MARKET_HISTORY_BATCH_SIZE = 200
MARKET_HISTORY_FAILURE_LIMIT = 20

type ResultReporter = Callable[[int, int, MarketHistoryUpdateResult], None]


@dataclass(slots=True, kw_only=True)
class MarketHistoryBulkResult:
    """Run totals, including scheduled cancellations and unscheduled pairs.

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
        """Number of pairs never scheduled."""
        return self.total - self.completed - self.cancelled


async def update_market_histories(
    esi_link: EsiLink,
    schema: EsiSchema,
    connection: Connection,
    *,
    region_ids: set[int],
    type_ids: set[int],
    on_result: ResultReporter | None = None,
    batch_size: int = MARKET_HISTORY_BATCH_SIZE,
    failure_limit: int = MARKET_HISTORY_FAILURE_LIMIT,
) -> MarketHistoryBulkResult:
    """Update unique region/type pairs in concurrent, nonoverlapping batches.

    Args:
        esi_link: Shared ESI client, including its caching and rate limiting.
        schema: ESI request schema.
        connection: History connection used only on the event-loop thread.
        region_ids: Validated region IDs.
        type_ids: Selected published market type IDs.
        on_result: Optional synchronous reporter called for each completed pair.
        batch_size: Number of pairs to process concurrently.
        failure_limit: Maximum number of failed pairs before aborting.

    Returns:
        Totals after all pairs finish or the global failure limit is reached.
        On abort, pending tasks are cancelled and awaited before returning.

    Ordinary updater exceptions are logged and counted as failed pairs. External
    cancellation propagates after child cleanup and is not an update failure.
    """
    summary = MarketHistoryBulkResult(total=len(region_ids) * len(type_ids))
    pairs = product(sorted(region_ids), sorted(type_ids))
    tasks: list[asyncio.Task[None]] = []

    async def update_pair(region_id: int, type_id: int) -> None:
        result: MarketHistoryUpdateResult
        try:
            result = await update_market_history(
                esi_link, schema, connection, region_id=region_id, type_id=type_id
            )
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

    for batch in batched(pairs, batch_size, strict=False):
        async with asyncio.TaskGroup() as group:
            tasks = [
                group.create_task(update_pair(region_id, type_id))
                for region_id, type_id in batch
            ]
        summary.cancelled += sum(task.cancelled() for task in tasks)
        if summary.aborted:
            break
    return summary
