"""Tests for bounded, failure-limited concurrent market-history updates."""

import asyncio
import sqlite3
from unittest.mock import AsyncMock, Mock

import pytest
from pfmsoft.eve_link import EsiLink, EsiRequest, EsiResponse, EsiSchema
from whenever import Instant

from pfmsoft.eve_argus.fetch_esi import market_history_bulk as bulk
from pfmsoft.eve_argus.fetch_esi.update import UpdateResult, UpdateStatus
from pfmsoft.eve_argus.market_history.models import MarketHistoryResponse
from pfmsoft.eve_argus.market_history.util import load_table_definitions


def _result(
    status: UpdateStatus = UpdateStatus.UPDATED,
) -> UpdateResult[MarketHistoryResponse]:
    """Build an update outcome for orchestration tests."""
    return UpdateResult(
        status=status,
        previous_state=None,
        failure_message="test failure" if status is UpdateStatus.FAILED else None,
    )


def test_constants() -> None:
    """Production limits are 100 tasks and 20 failures."""
    assert bulk.MARKET_HISTORY_BATCH_SIZE == 100
    assert bulk.MARKET_HISTORY_FAILURE_LIMIT == 20


def test_batches_overlap_but_never_exceed_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial final batch runs, and batches do not overlap each other."""

    async def scenario() -> None:
        active = 0
        maximum = 0
        started = 0
        completed = 0
        gates = [asyncio.Event() for _ in range(3)]
        pairs: set[tuple[int, int]] = set()

        async def update(
            *args: object, region_id: int, type_id: int
        ) -> UpdateResult[MarketHistoryResponse]:
            nonlocal active, maximum, started, completed
            batch = started // 100
            assert completed >= batch * 100
            started += 1
            active += 1
            maximum = max(maximum, active)
            pairs.add((region_id, type_id))
            if active == (5 if batch == 2 else 100):
                gates[batch].set()
            await gates[batch].wait()
            active -= 1
            completed += 1
            return _result()

        monkeypatch.setattr(bulk, "update_market_history", update)
        summary = await asyncio.wait_for(
            bulk.update_market_histories(
                Mock(spec=EsiLink),
                Mock(spec=EsiSchema),
                Mock(spec=sqlite3.Connection),
                region_ids={10},
                type_ids=set(range(205)),
            ),
            timeout=5,
        )
        assert maximum == 100
        assert len(pairs) == 205
        assert summary.updated == summary.total == 205
        assert summary.failed == summary.cancelled == summary.not_started == 0
        assert not summary.aborted

    asyncio.run(scenario())


@pytest.mark.parametrize("failures", [19, 20])
def test_global_failure_threshold(
    monkeypatch: pytest.MonkeyPatch, *, failures: int
) -> None:
    """Nineteen failures continue across regions/batches; twenty abort."""
    monkeypatch.setattr(bulk, "MARKET_HISTORY_BATCH_SIZE", 5)
    calls: list[tuple[int, int]] = []

    async def update(
        *args: object, region_id: int, type_id: int
    ) -> UpdateResult[MarketHistoryResponse]:
        calls.append((region_id, type_id))
        if len(calls) <= failures:
            if len(calls) % 2:
                raise RuntimeError("fetch raised")
            return _result(UpdateStatus.FAILED)
        return _result(UpdateStatus.SKIPPED)

    monkeypatch.setattr(bulk, "update_market_history", update)
    reported: list[str] = []
    summary = asyncio.run(
        bulk.update_market_histories(
            Mock(spec=EsiLink),
            Mock(spec=EsiSchema),
            Mock(spec=sqlite3.Connection),
            region_ids={11, 10},
            type_ids=set(range(12)),
            on_result=lambda region_id, type_id, result: reported.append(result.status),
        )
    )
    assert summary.failed == failures
    assert calls == sorted(calls)
    if failures == 19:
        assert len(calls) == 24
        assert summary.skipped == 5
        assert not summary.aborted
    else:
        assert len(calls) == 20
        assert summary.not_started == 4
        assert summary.aborted
    assert len(reported) == len(calls)


def test_abort_cancels_pending_and_preserves_commits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Abort awaits cleanup and does not roll back already committed updates."""
    monkeypatch.setattr(bulk, "MARKET_HISTORY_BATCH_SIZE", 5)
    monkeypatch.setattr(bulk, "MARKET_HISTORY_FAILURE_LIMIT", 2)

    async def scenario(connection: sqlite3.Connection) -> None:
        ready = asyncio.Event()
        blocked = asyncio.Event()
        started = 0
        cleaned: set[int] = set()

        async def update(
            *args: object, region_id: int, type_id: int
        ) -> UpdateResult[MarketHistoryResponse]:
            nonlocal started
            started += 1
            if started == 5:
                ready.set()
            try:
                await ready.wait()
                if type_id == 0:
                    with connection:
                        connection.execute("INSERT INTO saved VALUES (0)")
                    return _result()
                if type_id in (1, 2):
                    return _result(UpdateStatus.FAILED)
                await blocked.wait()
            finally:
                if type_id in (3, 4):
                    cleaned.add(type_id)
            return _result()

        monkeypatch.setattr(bulk, "update_market_history", update)
        summary = await bulk.update_market_histories(
            Mock(spec=EsiLink),
            Mock(spec=EsiSchema),
            connection,
            region_ids={10},
            type_ids=set(range(8)),
        )
        assert summary.aborted
        assert summary.updated == 1
        assert summary.failed == 2
        assert summary.cancelled == 2
        assert summary.not_started == 3
        assert cleaned == {3, 4}
        assert connection.execute("SELECT * FROM saved").fetchall() == [(0,)]

    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE saved (id INTEGER)")
        asyncio.run(asyncio.wait_for(scenario(connection), timeout=5))
    connection.close()


def test_parent_cancellation_is_not_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """External cancellation propagates only after child tasks have cleaned up."""

    async def scenario() -> None:
        ready = asyncio.Event()
        forever = asyncio.Event()
        cleaned: set[int] = set()
        started = 0

        async def update(
            *args: object, region_id: int, type_id: int
        ) -> UpdateResult[MarketHistoryResponse]:
            nonlocal started
            started += 1
            if started == 3:
                ready.set()
            try:
                await forever.wait()
            finally:
                cleaned.add(type_id)
            return _result()

        monkeypatch.setattr(bulk, "update_market_history", update)
        task = asyncio.create_task(
            bulk.update_market_histories(
                Mock(spec=EsiLink),
                Mock(spec=EsiSchema),
                Mock(spec=sqlite3.Connection),
                region_ids={10},
                type_ids={1, 2, 3},
            )
        )
        await ready.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cleaned == {1, 2, 3}

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))


def test_empty_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    """No selected types creates no tasks and succeeds."""
    update = Mock()
    monkeypatch.setattr(bulk, "update_market_history", update)
    summary = asyncio.run(
        bulk.update_market_histories(
            Mock(spec=EsiLink),
            Mock(spec=EsiSchema),
            Mock(spec=sqlite3.Connection),
            region_ids={10},
            type_ids=set(),
        )
    )
    assert summary.total == summary.not_started == 0
    assert not summary.aborted
    update.assert_not_called()


def test_reconciles_updates_finishing_during_abort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In-flight outcomes are counted even if cancellation cannot stop them."""
    monkeypatch.setattr(bulk, "MARKET_HISTORY_FAILURE_LIMIT", 1)

    async def scenario() -> None:
        started = asyncio.Event()
        forever = asyncio.Event()

        async def update(
            *args: object, region_id: int, type_id: int
        ) -> UpdateResult[MarketHistoryResponse]:
            if type_id == 0:
                await started.wait()
                return _result(UpdateStatus.FAILED)
            started.set()
            try:
                await forever.wait()
            except asyncio.CancelledError:
                return _result(UpdateStatus.FAILED)
            return _result()

        monkeypatch.setattr(bulk, "update_market_history", update)
        summary = await bulk.update_market_histories(
            Mock(spec=EsiLink),
            Mock(spec=EsiSchema),
            Mock(spec=sqlite3.Connection),
            region_ids={10},
            type_ids={0, 1},
        )
        assert summary.aborted
        assert summary.total == summary.failed == 2
        assert summary.cancelled == summary.not_started == 0

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))


def test_real_updater_persists_pairs_and_skips_current_data() -> None:
    """Concurrent mocked ESI responses use the production validator and writer."""

    async def scenario(connection: sqlite3.Connection) -> None:
        gate = asyncio.Event()
        requests = 0

        async def request(*, esi_request: EsiRequest, schema: EsiSchema) -> Mock:
            nonlocal requests
            requests += 1
            if requests == 4:
                gate.set()
            await gate.wait()
            response = Mock(spec=EsiResponse)
            response.esi_request = esi_request
            response.response.metadata.received_at = "2026-10-18T00:00:00Z"
            response.response.metadata.expires_at_instant = Instant.parse_iso(
                "2999-01-01T00:00:00Z"
            )
            response.response_data = [
                {
                    "average": 1.25,
                    "highest": 2.0,
                    "lowest": 1.0,
                    "date": "2026-10-17",
                    "order_count": 2,
                    "volume": 3,
                }
            ]
            return response

        esi_link = Mock(spec=EsiLink)
        esi_link.make_request = AsyncMock(side_effect=request)
        schema = Mock(spec=EsiSchema)
        summary = await bulk.update_market_histories(
            esi_link,
            schema,
            connection,
            region_ids={10, 11},
            type_ids={20, 21},
        )
        assert summary.updated == 4
        assert summary.failed == 0
        assert connection.execute(
            "SELECT region_id, type_id, average FROM market_history "
            "ORDER BY region_id, type_id"
        ).fetchall() == [(10, 20, 125), (10, 21, 125), (11, 20, 125), (11, 21, 125)]
        assert connection.execute(
            "SELECT COUNT(*) FROM market_history_response"
        ).fetchone() == (4,)
        cached = await bulk.update_market_histories(
            esi_link,
            schema,
            connection,
            region_ids={10, 11},
            type_ids={20, 21},
        )
        assert cached.skipped == 4
        assert cached.failed == 0
        assert esi_link.make_request.await_count == 4

    with sqlite3.connect(":memory:") as connection:
        connection.executescript(load_table_definitions())
        asyncio.run(asyncio.wait_for(scenario(connection), timeout=5))
    connection.close()
