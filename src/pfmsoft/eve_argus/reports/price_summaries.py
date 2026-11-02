"""Collect region- or system-scoped prices from stored market-order snapshots."""

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Literal

from whenever import Instant

from pfmsoft.eve_argus.dynamic.models import (
    MarketOrdersResponse,
    OrderSummaryDataset,
    OrderSummaryRecord,
    ResponseMetadata,
)
from pfmsoft.eve_argus.dynamic.order_summary import (
    FILTER_FACTOR_DEFAULT,
    validate_summary_options,
)
from pfmsoft.eve_argus.reports.market_hub_prices import PriceSummaryMetrics
from pfmsoft.eve_argus.static.models import MarketGroupsDataset, TypesDataset


@dataclass(slots=True, kw_only=True, frozen=True)
class PriceSummaryRow:
    """One type's prices, retaining nullable buy and sell sides independently."""

    type_id: int
    type_name: str
    market_group_id: int | None
    market_group_name: str | None
    market_path_ids: tuple[int, ...] | None
    market_path_names: tuple[str, ...] | None
    buy_summary: PriceSummaryMetrics | None
    sell_summary: PriceSummaryMetrics | None


@dataclass(slots=True, kw_only=True, frozen=True)
class PriceSummariesReport(ResponseMetadata):
    """A price report tied to one source region snapshot."""

    schema_version: Literal[2]
    scope: Literal["region", "system"]
    region_id: int
    region_name: str
    system_id: int | None
    system_name: str | None
    filter_factor: Decimal
    generated_at: str
    is_stale: bool | None
    records: tuple[PriceSummaryRow, ...]


def _collect_metrics(
    *,
    summary: OrderSummaryRecord | None,
    type_id: int,
    region_id: int,
    system_id: int | None,
    is_buy: bool,
) -> PriceSummaryMetrics | None:
    """Validate side identity and copy exact calculated metrics."""
    if summary is None:
        return None
    if (
        summary.type_id != type_id
        or summary.region_id != region_id
        or summary.system_id != system_id
        or summary.location_id is not None
        or summary.is_buy_summary != is_buy
    ):
        raise ValueError(f"Invalid summary identity, scope or side for type {type_id}.")
    return PriceSummaryMetrics(
        five_price=summary.five_price,
        five_orders=summary.five_orders,
        five_items=summary.five_items,
        lowest=summary.lowest,
        highest=summary.highest,
        average=summary.average,
        total_items=summary.total_items,
        total_orders=summary.total_orders,
        filtered_items=summary.filtered_items,
        filtered_orders=summary.filtered_orders,
    )


def collect_price_summaries(
    *,
    summaries: OrderSummaryDataset,
    response: MarketOrdersResponse,
    region_name: str,
    system_name: str | None,
    types: TypesDataset,
    market_groups: MarketGroupsDataset,
    generated_at: Instant,
    filter_factor: Decimal = FILTER_FACTOR_DEFAULT,
) -> PriceSummariesReport:
    """Validate and enrich a calculated dataset for its declared scope.

    Types without either buy or sell summaries are omitted. Argus expiry takes
    precedence over source expiry when determining freshness.

    Raises:
        ValueError: If scope, provenance, summary identity, or static references
            disagree.
    """
    validate_summary_options(
        system_id=summaries.system_id,
        location_id=None,
        filter_factor=filter_factor,
    )
    if summaries.location_id is not None:
        raise ValueError("Price summaries do not support station-scoped datasets.")
    if (summaries.system_id is None) != (system_name is None):
        raise ValueError("System ID and system name must either both be set or unset.")
    for key, value in asdict(response).items():
        if getattr(summaries, key) != value:
            raise ValueError(f"Summary response and dataset disagree on {key}.")
    Instant.parse_iso(summaries.received_at)
    for expiry in (summaries.expires_at, summaries.argus_expires_at):
        if expiry is not None:
            Instant.parse_iso(expiry)

    rows: list[PriceSummaryRow] = []
    for type_id, sides in sorted(summaries.records.items()):
        if sides.buy_summary is None and sides.sell_summary is None:
            continue
        type_record = types.get(type_id)
        if type_record is None or type_record.type_id != type_id:
            raise ValueError(f"Missing or inconsistent static type {type_id}.")
        group = None
        if type_record.market_group_id is not None:
            group = market_groups.get(type_record.market_group_id)
            if group is None or group.market_group_id != type_record.market_group_id:
                raise ValueError(
                    "Missing or inconsistent static market group "
                    f"{type_record.market_group_id}."
                )
            if (
                not group.int_path
                or len(group.int_path) != len(group.str_path)
                or group.int_path[-1] != group.market_group_id
                or group.str_path[-1] != group.name
            ):
                raise ValueError(
                    f"Invalid static market path for group {group.market_group_id}."
                )
        rows.append(
            PriceSummaryRow(
                type_id=type_id,
                type_name=type_record.name,
                market_group_id=type_record.market_group_id,
                market_group_name=group.name if group is not None else None,
                market_path_ids=group.int_path if group is not None else None,
                market_path_names=group.str_path if group is not None else None,
                buy_summary=_collect_metrics(
                    summary=sides.buy_summary,
                    type_id=type_id,
                    region_id=summaries.region_id,
                    system_id=summaries.system_id,
                    is_buy=True,
                ),
                sell_summary=_collect_metrics(
                    summary=sides.sell_summary,
                    type_id=type_id,
                    region_id=summaries.region_id,
                    system_id=summaries.system_id,
                    is_buy=False,
                ),
            )
        )

    expiry = summaries.argus_expires_at or summaries.expires_at
    return PriceSummariesReport(
        schema_version=2,
        scope="region" if summaries.system_id is None else "system",
        region_id=summaries.region_id,
        region_name=region_name,
        system_id=summaries.system_id,
        system_name=system_name,
        filter_factor=filter_factor,
        response_metadata_id=summaries.response_metadata_id,
        received_at=summaries.received_at,
        expires_at=summaries.expires_at,
        argus_expires_at=summaries.argus_expires_at,
        generated_at=generated_at.format_iso(),
        is_stale=Instant.parse_iso(expiry) <= generated_at
        if expiry is not None
        else None,
        records=tuple(rows),
    )
