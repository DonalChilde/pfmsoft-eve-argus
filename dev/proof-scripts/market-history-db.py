"""Proof script for the market history database.

Downloads market history for the first three ship rig type IDs in every market hub
region, writes it to the market history database, and exercises every
MarketHistoryReader method. A second download then proves the update path: each
(region, type) gains one response row while history rows are replaced, not duplicated.

Run from the project root with `uv run dev/proof-scripts/market-history-db.py` so the
dev environment settings are used.
"""

import asyncio
import json
from dataclasses import asdict, dataclass, field
from logging import basicConfig
from pathlib import Path
from sqlite3 import Connection

from pfmsoft.eve_argus.data_loaders.esi_responses import EsiResponseLoader
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.helpers.market_groups import filter_type_ids_by_market_path
from pfmsoft.eve_argus.market.history.access import (
    MarketHistoryReader,
    MarketHistoryWrite,
)
from pfmsoft.eve_argus.market.history.db.models import MarketHistoryRecord
from pfmsoft.eve_argus.models.argus.static import MarketGroupsDataset
from pfmsoft.eve_argus.models.esi.esi_response_models import (
    GetMarketsRegionIdHistory,
)
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS
from pfmsoft.eve_argus.settings import get_settings
from pfmsoft.eve_argus.static.access import ArgusStaticDBQuery

SCRIPT_NAME = "market-history-db"
PROOF_SCRIPTS_DIR = Path(__file__).parent
LOG_FILE_PATH = PROOF_SCRIPTS_DIR / "logging" / f"{SCRIPT_NAME}.log"
REPORT_PATH = (
    PROOF_SCRIPTS_DIR / "proof-output" / "market-history" / f"{SCRIPT_NAME}-report.json"
)
SHIP_RIGS_STR_PATH = ("Ship and Module Modifications", "Rigs")
TYPE_ID_COUNT = 3
LATEST_COUNT = 5
DATE_RANGE_SPAN = 7

type RegionTypeKey = tuple[int, int]


@dataclass(slots=True, kw_only=True)
class RowCounts:
    """Row counts for a single (region, type) pair."""

    history_rows: int
    response_rows: int


@dataclass(slots=True, kw_only=True)
class PairReport:
    """Report entry for a single (region, type) pair."""

    region_id: int
    region_name: str
    type_id: int
    before_first_download: RowCounts
    after_first_download: RowCounts
    after_update: RowCounts
    first_received_at: str
    update_received_at: str
    latest_records: list[MarketHistoryRecord] = field(
        default_factory=list[MarketHistoryRecord]
    )


def setup_logging() -> None:
    """Configure file logging for this proof script."""
    LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    basicConfig(
        filename=LOG_FILE_PATH,
        level="INFO",
        format="%(asctime)s | %(levelname)-8s | %(funcName)s | %(message)s | [in %(pathname)s | %(lineno)d]",
    )


def resolve_market_group_id(
    market_groups: MarketGroupsDataset, *, str_path: tuple[str, ...]
) -> int:
    """Find the market group ID whose name path matches str_path exactly.

    Args:
        market_groups: The market groups dataset.
        str_path: The full path of market group names, root first.

    Returns:
        The matching market group ID.

    Raises:
        ValueError: If zero or more than one market group matches.
    """
    matches = [
        group_id
        for group_id, group in market_groups.items()
        if tuple(group.str_path) == str_path
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one market group for {str_path}, found {matches}")
    return matches[0]


def select_type_ids(
    market_groups: MarketGroupsDataset, *, str_path: tuple[str, ...], count: int
) -> list[int]:
    """Select the lowest `count` type IDs under a market group path.

    Args:
        market_groups: The market groups dataset.
        str_path: The full path of market group names, root first.
        count: The number of type IDs to select.

    Returns:
        Sorted type IDs, at most `count` long.
    """
    group_id = resolve_market_group_id(market_groups, str_path=str_path)
    type_ids = filter_type_ids_by_market_path(market_groups, include={group_id})
    return sorted(type_ids)[:count]


async def download_and_write(
    *,
    loader: EsiResponseLoader,
    connection: Connection,
    region_ids: list[int],
    type_ids: list[int],
) -> dict[RegionTypeKey, GetMarketsRegionIdHistory]:
    """Download market history for every region and type, and write it to the db.

    Args:
        loader: The ESI response loader.
        connection: The market history database connection.
        region_ids: Region IDs to download.
        type_ids: Type IDs to download for each region.

    Returns:
        The downloaded histories keyed by (region_id, type_id).
    """
    writer = MarketHistoryWrite()
    downloaded: dict[RegionTypeKey, GetMarketsRegionIdHistory] = {}
    for region_id in region_ids:
        response = await loader.region_market_histories(
            region_id=region_id, type_ids=set(type_ids)
        )
        for history in response.response_data:
            writer.write_market_history(connection, history)
            downloaded[(history.region_id, history.type_id)] = history
    expected = {(r, t) for r in region_ids for t in type_ids}
    assert set(downloaded) == expected, (
        f"Missing downloads: {expected - set(downloaded)}"
    )
    return downloaded


def snapshot_counts(
    connection: Connection, *, keys: list[RegionTypeKey]
) -> dict[RegionTypeKey, RowCounts]:
    """Record history and response row counts for each (region, type) pair."""
    reader = MarketHistoryReader()
    return {
        (region_id, type_id): RowCounts(
            history_rows=len(
                reader.read_market_history(connection, region_id, type_id)
            ),
            response_rows=len(
                reader.read_market_history_responses(connection, region_id, type_id)
            ),
        )
        for region_id, type_id in keys
    }


def check_read_market_history(
    connection: Connection, *, region_id: int, type_id: int, expected_rows: int
) -> tuple[MarketHistoryRecord, ...]:
    """Check read_market_history returns matching rows, newest first."""
    records = MarketHistoryReader().read_market_history(connection, region_id, type_id)
    assert len(records) == expected_rows, (
        f"{region_id}/{type_id}: expected {expected_rows} rows, got {len(records)}"
    )
    assert all(r.region_id == region_id and r.type_id == type_id for r in records)
    dates = [r.date for r in records]
    assert dates == sorted(dates, reverse=True), "History not ordered newest first"
    assert len(set(dates)) == len(dates), "Duplicate history dates found"
    return records


def check_read_market_history_latest(
    connection: Connection,
    *,
    region_id: int,
    type_id: int,
    full: tuple[MarketHistoryRecord, ...],
) -> tuple[MarketHistoryRecord, ...]:
    """Check read_market_history_latest matches the head of the full history."""
    reader = MarketHistoryReader()
    latest = reader.read_market_history_latest(
        connection, region_id, type_id, LATEST_COUNT
    )
    assert latest == full[:LATEST_COUNT], "Latest records do not match full history"
    try:
        reader.read_market_history_latest(connection, region_id, type_id, 0)
    except ValueError:
        pass
    else:
        raise AssertionError("count=0 should raise ValueError")
    return latest


def check_read_market_history_date_range(
    connection: Connection,
    *,
    region_id: int,
    type_id: int,
    full: tuple[MarketHistoryRecord, ...],
) -> None:
    """Check read_market_history_date_range against slices of the full history."""
    reader = MarketHistoryReader()
    unbounded = reader.read_market_history_date_range(
        connection, region_id, type_id, None, None
    )
    assert unbounded == full, "Unbounded date range does not match full history"
    if not full:
        return
    end_index = min(DATE_RANGE_SPAN, len(full)) - 1
    bounded = reader.read_market_history_date_range(
        connection, region_id, type_id, full[0].date, full[end_index].date
    )
    assert bounded == full[: end_index + 1], "Bounded date range mismatch"
    start_only = reader.read_market_history_date_range(
        connection, region_id, type_id, full[end_index].date, None
    )
    assert start_only == full[end_index:], "Start-only date range mismatch"


def check_read_market_history_responses(
    connection: Connection,
    *,
    region_id: int,
    type_id: int,
    expected_rows: int,
    received_at: str,
) -> None:
    """Check response metadata ordering and that the newest matches the download."""
    responses = MarketHistoryReader().read_market_history_responses(
        connection, region_id, type_id
    )
    assert len(responses) == expected_rows, (
        f"{region_id}/{type_id}: expected {expected_rows} responses, "
        f"got {len(responses)}"
    )
    ordering = [(r.received_at, r.response_metadata_id) for r in responses]
    assert ordering == sorted(ordering, reverse=True), "Responses not newest first"
    assert responses[0].received_at == received_at, "Newest response mismatch"


def check_read_market_history_responses_by_region(
    connection: Connection, *, region_id: int, type_ids: list[int]
) -> None:
    """Check by-region responses include each type and match the per-type read."""
    reader = MarketHistoryReader()
    by_region = reader.read_market_history_responses_by_region(
        connection, region_id=region_id
    )
    for type_id in type_ids:
        assert type_id in by_region, f"Type {type_id} missing in region {region_id}"
        assert by_region[type_id] == reader.read_market_history_responses(
            connection, region_id, type_id
        ), f"By-region responses mismatch for {region_id}/{type_id}"


def exercise_reader(
    connection: Connection,
    *,
    downloaded: dict[RegionTypeKey, GetMarketsRegionIdHistory],
    expected: dict[RegionTypeKey, RowCounts],
    type_ids: list[int],
) -> dict[RegionTypeKey, tuple[MarketHistoryRecord, ...]]:
    """Run every MarketHistoryReader check for all downloaded pairs.

    Returns:
        The latest records for each (region, type) pair.
    """
    latest_by_key: dict[RegionTypeKey, tuple[MarketHistoryRecord, ...]] = {}
    for (region_id, type_id), history in downloaded.items():
        counts = expected[(region_id, type_id)]
        full = check_read_market_history(
            connection,
            region_id=region_id,
            type_id=type_id,
            expected_rows=counts.history_rows,
        )
        latest_by_key[(region_id, type_id)] = check_read_market_history_latest(
            connection, region_id=region_id, type_id=type_id, full=full
        )
        check_read_market_history_date_range(
            connection, region_id=region_id, type_id=type_id, full=full
        )
        check_read_market_history_responses(
            connection,
            region_id=region_id,
            type_id=type_id,
            expected_rows=counts.response_rows,
            received_at=history.received_at,
        )
    for region_id in {region_id for region_id, _ in downloaded}:
        check_read_market_history_responses_by_region(
            connection, region_id=region_id, type_ids=type_ids
        )
    return latest_by_key


def snapshot_dates(
    connection: Connection, *, keys: list[RegionTypeKey]
) -> dict[RegionTypeKey, set[str]]:
    """Record the stored history dates for each (region, type) pair."""
    reader = MarketHistoryReader()
    return {
        (region_id, type_id): {
            r.date for r in reader.read_market_history(connection, region_id, type_id)
        }
        for region_id, type_id in keys
    }


def expected_after_download(
    *,
    before_counts: dict[RegionTypeKey, RowCounts],
    before_dates: dict[RegionTypeKey, set[str]],
    downloaded: dict[RegionTypeKey, GetMarketsRegionIdHistory],
) -> dict[RegionTypeKey, RowCounts]:
    """Compute expected counts after a download is written.

    History rows are replaced on (region, type, date) conflict, so stored rows are the
    union of previously stored dates and downloaded dates. Each download adds exactly
    one response row.
    """
    return {
        key: RowCounts(
            history_rows=len(
                before_dates[key] | {d.date for d in downloaded[key].history}
            ),
            response_rows=before_counts[key].response_rows + 1,
        )
        for key in downloaded
    }


def print_summary(reports: list[PairReport]) -> None:
    """Print a per (region, type) summary table."""
    header = (
        f"{'region':<14}{'type_id':>9}{'history':>9}{'responses':>11}"
        f"{'newest date':>13}  received_at"
    )
    print(header)
    print("-" * len(header))
    for report in reports:
        newest = report.latest_records[0].date if report.latest_records else "-"
        print(
            f"{report.region_name:<14}{report.type_id:>9}"
            f"{report.after_update.history_rows:>9}"
            f"{report.after_update.response_rows:>11}"
            f"{newest:>13}  {report.update_received_at}"
        )


def write_report(*, type_ids: list[int], reports: list[PairReport]) -> None:
    """Write the JSON proof report."""
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"type_ids": type_ids, "pairs": [asdict(r) for r in reports]}
    REPORT_PATH.write_text(json.dumps(payload, indent=2, default=str))
    print(f"Report written to {REPORT_PATH}")


async def prove_market_history_db() -> None:
    """Download, write, read, and update market history for hub regions."""
    settings = get_settings()
    print(f"Market history database: {settings.market_history_database}")
    async with EveArgusResources(settings=settings) as resources:
        market_groups = ArgusStaticDBQuery().market_groups(
            resources.argus_static_db_connection
        )
        type_ids = select_type_ids(
            market_groups, str_path=SHIP_RIGS_STR_PATH, count=TYPE_ID_COUNT
        )
        assert len(type_ids) == TYPE_ID_COUNT, f"Too few ship rig types: {type_ids}"
        print(f"Ship rig type IDs: {type_ids}")

        region_ids = [hub.region_id for hub in MARKET_HUBS]
        region_names = {hub.region_id: hub.region_name for hub in MARKET_HUBS}
        keys = [(r, t) for r in region_ids for t in type_ids]
        connection = resources.market_history_db_connection
        loader = EsiResponseLoader(
            esi_link=resources.esi_link, schema=resources.esi_schema
        )

        before_first = snapshot_counts(connection, keys=keys)
        before_first_dates = snapshot_dates(connection, keys=keys)
        first = await download_and_write(
            loader=loader,
            connection=connection,
            region_ids=region_ids,
            type_ids=type_ids,
        )
        after_first = expected_after_download(
            before_counts=before_first,
            before_dates=before_first_dates,
            downloaded=first,
        )
        exercise_reader(
            connection, downloaded=first, expected=after_first, type_ids=type_ids
        )
        print("First download: all reader checks passed.")

        update = await download_and_write(
            loader=loader,
            connection=connection,
            region_ids=region_ids,
            type_ids=type_ids,
        )
        after_update = {
            key: RowCounts(
                history_rows=after_first[key].history_rows,
                response_rows=after_first[key].response_rows + 1,
            )
            for key in keys
        }
        latest_by_key = exercise_reader(
            connection, downloaded=update, expected=after_update, type_ids=type_ids
        )
        for key in keys:
            # ESI caches history for up to 24 hours, so the update is the same payload.
            assert update[key].received_at == first[key].received_at, (
                f"{key}: received_at changed on update"
            )
        print("Update download: all reader checks passed.")

    reports = [
        PairReport(
            region_id=region_id,
            region_name=region_names[region_id],
            type_id=type_id,
            before_first_download=before_first[(region_id, type_id)],
            after_first_download=after_first[(region_id, type_id)],
            after_update=after_update[(region_id, type_id)],
            first_received_at=first[(region_id, type_id)].received_at,
            update_received_at=update[(region_id, type_id)].received_at,
            latest_records=list(latest_by_key[(region_id, type_id)]),
        )
        for region_id, type_id in keys
    ]
    print_summary(reports)
    write_report(type_ids=type_ids, reports=reports)


if __name__ == "__main__":
    setup_logging()
    asyncio.run(prove_market_history_db())
