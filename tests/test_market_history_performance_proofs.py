"""Offline tests for the proof-only history performance harness."""

import argparse
import asyncio
import importlib
import json
import sqlite3
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, Mock

import pytest
from pfmsoft.eve_link import EsiLink, EsiSchema

from pfmsoft.eve_argus.fetch_esi.update import UpdateResult, UpdateStatus
from pfmsoft.eve_argus.market_history.models import MarketHistoryResponse
from pfmsoft.eve_argus.static.models import MarketGroupsRecord, TypesRecord


@pytest.fixture
def proof(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import proof helpers without running a benchmark or acquiring resources."""
    directory = Path(__file__).resolve().parents[1] / (
        "dev/proof-scripts/market-history-performance"
    )
    monkeypatch.setattr(sys, "path", [str(directory), *sys.path])
    return importlib.import_module("_benchmark")


def test_worker_refills_before_slow_pair_finishes(
    proof: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two workers stay bounded and replace completed work without a barrier."""

    async def scenario() -> None:
        slow = asyncio.Event()
        active = 0
        peak = 0
        calls: list[int] = []

        async def update(
            *args: object, region_id: int, type_id: int
        ) -> UpdateResult[MarketHistoryResponse]:
            nonlocal active, peak
            assert region_id == 10000002
            active += 1
            peak = max(peak, active)
            calls.append(type_id)
            if type_id == 0:
                await slow.wait()
            if type_id == 4:
                slow.set()
            active -= 1
            return UpdateResult(status=UpdateStatus.UPDATED, previous_state=None)

        monkeypatch.setattr(proof, "update_market_history", update)
        reporter = Mock()
        result = await proof.run_workers(
            Mock(spec=EsiLink),
            Mock(spec=EsiSchema),
            Mock(spec=sqlite3.Connection),
            type_ids=list(range(5)),
            concurrency=2,
            on_result=reporter,
        )
        assert calls == list(range(5))
        assert peak == 2
        assert result.updated == 5
        assert result.failed == result.cancelled == result.not_started == 0
        assert reporter.call_count == 5

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))


def test_worker_failure_limit_and_cleanup(
    proof: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exceptions and failed results count; active cancellation is awaited."""
    monkeypatch.setattr(proof, "MARKET_HISTORY_FAILURE_LIMIT", 2)

    async def scenario() -> None:
        ready = asyncio.Event()
        blocked = asyncio.Event()
        cleaned: list[int] = []

        async def update(
            *args: object, region_id: int, type_id: int
        ) -> UpdateResult[MarketHistoryResponse]:
            if type_id == 0:
                try:
                    ready.set()
                    await blocked.wait()
                finally:
                    cleaned.append(type_id)
            if type_id == 1:
                await ready.wait()
                raise RuntimeError("raised fetch error")
            return UpdateResult(
                status=UpdateStatus.FAILED,
                previous_state=None,
                failure_message="failed fetch",
            )

        monkeypatch.setattr(proof, "update_market_history", update)
        report = Mock()
        result = await proof.run_workers(
            Mock(spec=EsiLink),
            Mock(spec=EsiSchema),
            Mock(spec=sqlite3.Connection),
            type_ids=list(range(6)),
            concurrency=2,
            on_result=report,
        )
        assert result.aborted
        assert result.failed == 2
        assert result.cancelled == 1
        assert result.not_started == 3
        assert cleaned == [0]
        assert report.call_count == 2
        assert "RuntimeError" in report.call_args_list[0].args[2].failure_message

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))


def test_env_isolation_and_warm_cache_guard(
    proof: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Explicit env files, not root settings or environment overrides, select caches."""
    monkeypatch.setattr(proof, "ROOT", tmp_path)
    monkeypatch.delenv(f"{proof.ENV_PREFIX}APPLICATION_DIRECTORY", raising=False)
    env = tmp_path / "eve-argus.env.dev"
    env.write_text(
        "PFMSOFT_EVE_ARGUS_APPLICATION_DIRECTORY=dev/bench/app-dir\n",
        encoding="utf-8",
    )
    app = tmp_path / "dev/bench/app-dir"
    assert proof.application_directory(env) == app
    app.mkdir(parents=True)
    (app / "cache").write_text("warm", encoding="utf-8")
    with pytest.raises(ValueError, match="warm"):
        proof.application_directory(env)
    env.write_text(
        "PFMSOFT_EVE_ARGUS_APPLICATION_DIRECTORY=dev/app-dir\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="isolated"):
        proof.application_directory(env)
    monkeypatch.setenv(f"{proof.ENV_PREFIX}APPLICATION_DIRECTORY", "dev/other-app")
    with pytest.raises(ValueError, match="Unset"):
        proof.application_directory(env)


def test_selection_is_deterministic_and_published_market_only(
    proof: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both schedulers receive exactly the same sorted unique market type IDs."""
    group = MarketGroupsRecord(
        market_group_id=1,
        description="",
        has_types=True,
        icon_id=None,
        int_path=(1,),
        name="Group",
        parent_group_id=None,
        str_path=("Group",),
        types=(3, 2, 1),
    )
    monkeypatch.setattr(proof, "create_read_only_connection", Mock())
    monkeypatch.setattr(
        proof.read, "map_regions", Mock(return_value={10000002: Mock()})
    )
    types = Mock(return_value={key: Mock(spec=TypesRecord) for key in (4, 3, 1)})
    monkeypatch.setattr(proof.read, "types", types)
    monkeypatch.setattr(proof.read, "market_groups", Mock(return_value={1: group}))
    assert proof.select_types(Path("static.sqlite"), count=2) == [1, 3]
    assert types.call_args.kwargs["only_published"] is True
    with pytest.raises(ValueError, match="only 2"):
        proof.select_types(Path("static.sqlite"), count=3)


def test_positive_sizes(proof: ModuleType) -> None:
    """Invalid sizes cannot result in no-op benchmark successes."""
    assert proof.positive_int("2000") == 2000
    for value in ("0", "-1"):
        with pytest.raises(argparse.ArgumentTypeError):
            proof.positive_int(value)


@pytest.mark.parametrize("method", ["batch", "worker"])
def test_benchmark_setup_and_result_files(
    proof: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, method: str
) -> None:
    """Both entry points isolate settings, pass equal inputs, and save timed totals."""
    monkeypatch.setattr(proof, "ROOT", tmp_path)
    monkeypatch.delenv(f"{proof.ENV_PREFIX}APPLICATION_DIRECTORY", raising=False)
    env_file = tmp_path / "eve-argus.env.dev"
    directory = tmp_path / f"dev/{method}/app-dir"
    env_file.write_text(
        f"PFMSOFT_EVE_ARGUS_APPLICATION_DIRECTORY=dev/{method}/app-dir\n",
        encoding="utf-8",
    )
    directory.mkdir(parents=True)
    settings = Mock()
    settings.logging_directory = directory
    settings.market_history_database = directory / "history.sqlite"
    settings.compatibility_date = None
    settings.eve_link_settings.max_rate = 50
    settings.eve_link_settings.time_period = 1
    settings_factory = Mock(return_value=settings)
    monkeypatch.setattr(proof, "get_settings", settings_factory)
    selector = Mock(return_value=[34, 35])
    monkeypatch.setattr(proof, "select_types", selector)
    requests = Mock()
    client = Mock(spec=EsiLink)
    manager = Mock()
    manager.__aenter__ = AsyncMock(return_value=client)
    manager.__aexit__ = AsyncMock(return_value=False)
    requests.esi_link_factory.return_value = manager
    monkeypatch.setattr(proof, "SimpleRequests", Mock(return_value=requests))
    runner = AsyncMock(return_value=proof.MarketHistoryBulkResult(total=2, updated=2))
    monkeypatch.setattr(
        proof, "update_market_histories" if method == "batch" else "run_workers", runner
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "proof",
            "--env-file",
            str(env_file),
            "--static-db",
            str(tmp_path / "static"),
            "--count",
            "2",
            "--concurrency",
            "3",
        ],
    )
    proof.run_benchmark(method)
    settings_factory.assert_called_once_with(application_directory=directory)
    selector.assert_called_once_with(tmp_path / "static", count=2)
    runner.assert_awaited_once()
    kwargs = runner.call_args.kwargs
    if method == "batch":
        assert kwargs["batch_size"] == 3
        assert kwargs["region_ids"] == {10000002}
        assert kwargs["type_ids"] == {34, 35}
    else:
        assert kwargs["concurrency"] == 3
        assert kwargs["type_ids"] == [34, 35]
    results = json.loads((directory / "benchmark-result.json").read_text())
    assert results["updated"] == 2
    assert results["skipped"] == results["failed"] == 0
    assert results["elapsed_seconds"] > 0
    assert results["completed_pairs_per_minute"] > 0
    assert results["setup_and_run_seconds"] >= results["elapsed_seconds"]
    assert json.loads((directory / "type-ids.json").read_text()) == [34, 35]
    manager.__aexit__.assert_awaited_once()


def test_worker_parent_cancellation(
    proof: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Interruption propagates only after active workers have cleaned up."""

    async def scenario() -> None:
        ready = asyncio.Event()
        blocked = asyncio.Event()
        cleaned: set[int] = set()
        started = 0

        async def update(
            *args: object, region_id: int, type_id: int
        ) -> UpdateResult[MarketHistoryResponse]:
            nonlocal started
            started += 1
            if started == 2:
                ready.set()
            try:
                await blocked.wait()
            finally:
                cleaned.add(type_id)
            return UpdateResult(status=UpdateStatus.UPDATED, previous_state=None)

        monkeypatch.setattr(proof, "update_market_history", update)
        task = asyncio.create_task(
            proof.run_workers(
                Mock(spec=EsiLink),
                Mock(spec=EsiSchema),
                Mock(spec=sqlite3.Connection),
                type_ids=list(range(5)),
                concurrency=2,
                on_result=Mock(),
            )
        )
        await ready.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cleaned == {0, 1}

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))


def test_direct_fetch_proof_times_500_calls(
    proof: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fetch-only proof overlaps 500 calls and counts failures without DB writes."""
    direct = importlib.import_module("fetch_only")
    assert direct.CALL_COUNT == 500

    async def scenario() -> None:
        ready = asyncio.Event()
        calls: list[int] = []
        failed = Mock(spec=direct.FailedEsiResponse)
        failed.failed_response.error_messages = ["test failure"]

        async def fetch(*args: object, region_id: int, type_id: int) -> Mock:
            assert region_id == 10000002
            calls.append(type_id)
            if len(calls) == 500:
                ready.set()
            await ready.wait()
            if type_id == 0:
                raise RuntimeError("request raised")
            return failed if type_id == 1 else Mock(spec=direct.EsiLink)

        monkeypatch.setattr(direct, "market_history", fetch)
        result = await direct.time_fetches(
            Mock(spec=EsiLink), Mock(spec=EsiSchema), type_ids=list(range(500))
        )
        assert sorted(calls) == list(range(500))
        assert result.succeeded == 498
        assert result.failed == 2
        assert result.elapsed_seconds > 0

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))
