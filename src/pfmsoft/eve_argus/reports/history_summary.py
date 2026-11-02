"""Collect per-type summaries from stored regional market history."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from whenever import Instant

from pfmsoft.eve_argus.market_history.history_summary import (
    calculate_history_summary,
)
from pfmsoft.eve_argus.market_history.models import (
    HistorySummaryRecord,
    MarketHistoryRecord,
)
from pfmsoft.eve_argus.static.models import MarketGroupsDataset, TypesDataset


@dataclass(slots=True, kw_only=True, frozen=True)
class HistorySummaryInput:
    """Records and requested dates for one region/type pair."""

    type_id: int
    dates: tuple[str, ...]
    records: tuple[MarketHistoryRecord, ...]
    latest_record: MarketHistoryRecord | None


@dataclass(slots=True, kw_only=True, frozen=True)
class HistorySummaryRow:
    """One type's history summary, coverage, provenance, and market path."""

    type_id: int
    type_name: str
    market_group_id: int | None
    market_group_name: str | None
    market_path_ids: tuple[int, ...] | None
    market_path_names: tuple[str, ...] | None
    newest_date: str | None
    oldest_date: str | None
    missing_days: int | None
    highest_price: Decimal | None
    average_price: Decimal | None
    lowest_price: Decimal | None
    average_daily_order_count: int | None
    average_daily_volume: Decimal | None
    received_at: str | None
    expires_at: str | None
    argus_expires_at: str | None
    is_stale: bool | None


@dataclass(slots=True, kw_only=True, frozen=True)
class HistorySummaryReport:
    """One region's generated history summary export."""

    schema_version: Literal[1]
    report: Literal["history-summary"]
    generated_at: str
    region_id: int
    region_name: str
    period_days: int
    start_date: str | None
    records: tuple[HistorySummaryRow, ...]


def _validate_static_path(
    *,
    type_id: int,
    types: TypesDataset,
    market_groups: MarketGroupsDataset,
) -> tuple[int | None, str | None, tuple[int, ...] | None, tuple[str, ...] | None]:
    """Resolve and validate one type's static market-group path."""
    type_record = types.get(type_id)
    if type_record is None or type_record.type_id != type_id:
        raise ValueError(f"Missing or inconsistent static type {type_id}.")
    group_id = type_record.market_group_id
    if group_id is None:
        return None, None, None, None
    group = market_groups.get(group_id)
    if group is None or group.market_group_id != group_id:
        raise ValueError(f"Missing or inconsistent static market group {group_id}.")
    if (
        not group.int_path
        or len(group.int_path) != len(group.str_path)
        or group.int_path[-1] != group.market_group_id
        or group.str_path[-1] != group.name
    ):
        raise ValueError(
            f"Invalid static market path for group {group.market_group_id}."
        )
    return group_id, group.name, group.int_path, group.str_path


def _validate_record(
    record: MarketHistoryRecord, *, region_id: int, type_id: int
) -> None:
    """Validate provenance identity and parse timestamps before freshness checks."""
    if record.region_id != region_id or record.type_id != type_id:
        raise ValueError(
            f"History records do not match region {region_id}, type {type_id}."
        )
    Instant.parse_iso(record.received_at)
    for expiry in (record.expires_at, record.argus_expires_at):
        if expiry is not None:
            Instant.parse_iso(expiry)


def _collect_row(
    *,
    source: HistorySummaryInput,
    region_id: int,
    types: TypesDataset,
    market_groups: MarketGroupsDataset,
    generated_at: Instant,
) -> HistorySummaryRow:
    """Build one row, preserving latest provenance when its window is empty."""
    if source.type_id <= 0:
        raise ValueError(f"Invalid market-history type ID {source.type_id}.")
    for record in source.records:
        _validate_record(record, region_id=region_id, type_id=source.type_id)
    if source.latest_record is not None:
        _validate_record(
            source.latest_record, region_id=region_id, type_id=source.type_id
        )
    if source.records:
        summary: HistorySummaryRecord | None = calculate_history_summary(
            source.records, source.dates
        )
        metadata = summary
        newest_date = summary.start
        oldest_date = summary.end
        missing_days = summary.missing
        highest_price = summary.highest
        average_price = summary.average
        lowest_price = summary.lowest
        average_daily_order_count = summary.order_count
        average_daily_volume = summary.volume
    else:
        summary = None
        metadata = source.latest_record
        newest_date = max(source.dates) if source.dates else None
        oldest_date = min(source.dates) if source.dates else None
        missing_days = len(source.dates) if source.dates else None
        highest_price = None
        average_price = None
        lowest_price = None
        average_daily_order_count = None
        average_daily_volume = None

    expiry = (
        metadata.argus_expires_at or metadata.expires_at
        if metadata is not None
        else None
    )
    group_id, group_name, path_ids, path_names = _validate_static_path(
        type_id=source.type_id,
        types=types,
        market_groups=market_groups,
    )
    type_record = types[source.type_id]
    return HistorySummaryRow(
        type_id=source.type_id,
        type_name=type_record.name,
        market_group_id=group_id,
        market_group_name=group_name,
        market_path_ids=path_ids,
        market_path_names=path_names,
        newest_date=newest_date,
        oldest_date=oldest_date,
        missing_days=missing_days,
        highest_price=highest_price,
        average_price=average_price,
        lowest_price=lowest_price,
        average_daily_order_count=average_daily_order_count,
        average_daily_volume=average_daily_volume,
        received_at=metadata.received_at if metadata is not None else None,
        expires_at=metadata.expires_at if metadata is not None else None,
        argus_expires_at=metadata.argus_expires_at if metadata is not None else None,
        is_stale=Instant.parse_iso(expiry) <= generated_at if expiry else None,
    )


def collect_history_summary_report(
    *,
    region_id: int,
    region_name: str,
    period_days: int,
    start_date: str | None,
    summaries: tuple[HistorySummaryInput, ...],
    types: TypesDataset,
    market_groups: MarketGroupsDataset,
    generated_at: Instant,
) -> HistorySummaryReport:
    """Collect a deterministically ordered, statically enriched regional report.

    Raises:
        ValueError: If report options, provenance, or static references are invalid.
    """
    if region_id <= 0:
        raise ValueError("region_id must be positive.")
    if period_days <= 0:
        raise ValueError("period_days must be positive.")
    if (
        start_date is not None
        and date.fromisoformat(start_date).isoformat() != start_date
    ):
        raise ValueError("start_date must be an ISO date in YYYY-MM-DD format.")
    type_ids = [item.type_id for item in summaries]
    if len(type_ids) != len(set(type_ids)):
        raise ValueError("Duplicate type IDs in history summary inputs.")
    return HistorySummaryReport(
        schema_version=1,
        report="history-summary",
        generated_at=generated_at.format_iso(),
        region_id=region_id,
        region_name=region_name,
        period_days=period_days,
        start_date=start_date,
        records=tuple(
            _collect_row(
                source=source,
                region_id=region_id,
                types=types,
                market_groups=market_groups,
                generated_at=generated_at,
            )
            for source in sorted(summaries, key=lambda item: item.type_id)
        ),
    )
