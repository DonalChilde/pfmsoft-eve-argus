"""Collect corporation blueprint inventory and owned/missing original summaries."""

import logging
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Literal

from pfmsoft.eve_link import EsiLink, EsiResponse, EsiSchema, FailedEsiResponse
from whenever import Instant

from pfmsoft.eve_argus.dynamic.models import (
    CorporationBlueprintRecord,
    CorporationBlueprintsDataset,
    ResponseMetadata,
)
from pfmsoft.eve_argus.esi import fetch, validate
from pfmsoft.eve_argus.esi.models import (
    PostUniverseNamesCategory,
    PostUniverseNamesDetail,
)
from pfmsoft.eve_argus.static.models import MarketGroupsDataset, TypesDataset

logger = logging.getLogger(__name__)
type BlueprintKind = Literal["original", "stack", "copy"]


@dataclass(slots=True, kw_only=True, frozen=True)
class CorporationBlueprintReportRow(CorporationBlueprintRecord):
    """One original, stack, or copy with unmodified source fields and enrichment."""

    type_name: str
    published: bool
    market_group_id: int | None
    market_path: tuple[str, ...] | None
    location_name: str
    blueprint_kind: BlueprintKind
    item_count: int


@dataclass(slots=True, kw_only=True, frozen=True)
class OwnedBpoSummary:
    """All originals of one type with the ME/TE pair of one best actual item."""

    type_id: int
    name: str
    market_group_id: int | None
    market_path: tuple[str, ...] | None
    quantity: int
    selected_item_id: int
    material_efficiency: int
    time_efficiency: int
    in_comparison_universe: bool


@dataclass(slots=True, kw_only=True, frozen=True)
class MissingBpoRow:
    """A published market-blueprint type lacking an owned original, not a sale quote."""

    type_id: int
    name: str
    market_group_id: int
    market_path: tuple[str, ...]
    base_price: float | None


@dataclass(slots=True, kw_only=True, frozen=True)
class CorporationBlueprintsReport(ResponseMetadata):
    """Canonical report; Argus expiry takes precedence and None means unknown freshness."""

    corporation_id: int
    corporation_name: str
    generated_at: str
    is_stale: bool | None
    inventory: tuple[CorporationBlueprintReportRow, ...]
    owned_bpos: tuple[OwnedBpoSummary, ...]
    missing_bpos: tuple[MissingBpoRow, ...]
    warnings: tuple[str, ...]


def classify_blueprint_quantity(quantity: int) -> tuple[BlueprintKind, int]:
    """Classify ESI quantity sentinels without confusing copy runs with item counts.

    Raises:
        ValueError: If quantity is zero or an undocumented negative value.
    """
    match quantity:
        case -1:
            return "original", 1
        case -2:
            return "copy", 1
        case value if value > 0:
            return "stack", value
        case _:
            raise ValueError(f"Invalid blueprint quantity {quantity}.")


def collect_universe_name_ids(blueprints: CorporationBlueprintsDataset) -> set[int]:
    """Collect corporation and station-location IDs, never container/item IDs.

    The ESI asset location reference documents stations in [60000000, 64000000).
    Other namespaces, including asset safety, structures and containers, remain
    UNKNOWN. Range eligibility is not proof of a valid station: returned categories
    are checked and request failures are not suppressed.
    """
    return {blueprints.corporation_id} | {
        row.location_id
        for row in blueprints.records.values()
        if 60_000_000 <= row.location_id < 64_000_000
    }


def _comparison_universe(
    *,
    types: TypesDataset,
    market_groups: MarketGroupsDataset,
) -> set[int]:
    root = market_groups.get(2)
    if root is None or root.int_path != (2,):
        raise ValueError("Missing or invalid static blueprint market group root 2.")
    eligible: set[int] = set()
    for type_id, record in types.items():
        if record.type_id != type_id:
            raise ValueError(f"Static type key {type_id} disagrees with record ID.")
        if record.market_group_id is None:
            continue
        group = market_groups.get(record.market_group_id)
        if group is None:
            raise ValueError(f"Missing static market group {record.market_group_id}.")
        if record.published and 2 in group.int_path:
            eligible.add(type_id)
    return eligible


def _summarize_originals(
    inventory: tuple[CorporationBlueprintReportRow, ...],
    *,
    eligible: set[int],
) -> tuple[OwnedBpoSummary, ...]:
    grouped: dict[int, list[CorporationBlueprintReportRow]] = defaultdict(list)
    for row in inventory:
        if row.blueprint_kind != "copy":
            grouped[row.type_id].append(row)
    summaries: list[OwnedBpoSummary] = []
    for type_id, rows in grouped.items():
        best = max(
            rows,
            key=lambda row: (
                row.material_efficiency,
                row.time_efficiency,
                row.quantity,
                -row.item_id,
            ),
        )
        summaries.append(
            OwnedBpoSummary(
                type_id=type_id,
                name=best.type_name,
                market_group_id=best.market_group_id,
                market_path=best.market_path,
                quantity=sum(row.item_count for row in rows),
                selected_item_id=best.item_id,
                material_efficiency=best.material_efficiency,
                time_efficiency=best.time_efficiency,
                in_comparison_universe=type_id in eligible,
            )
        )
    return tuple(
        sorted(
            summaries,
            key=lambda row: (
                row.market_path is None,
                row.market_path or (),
                row.name,
                row.type_id,
            ),
        )
    )


async def collect_corporation_blueprints_report(
    *,
    blueprints: CorporationBlueprintsDataset,
    types: TypesDataset,
    market_groups: MarketGroupsDataset,
    esi_link: EsiLink,
    schema: EsiSchema,
    generated_at: Instant,
) -> CorporationBlueprintsReport:
    """Enrich a supplied snapshot and derive originals without database or file access.

    Load types with only_published=False. All owned types remain visible, but missing
    originals are compared only against published types beneath market group 2.
    Unsupported or omitted location names are UNKNOWN with diagnostics in JSON/logs.

    Raises:
        ValueError: For invalid quantities, timestamps, source/static references, or names.
        RuntimeError: If a universe-name request fails or no response is returned.
    """
    eligible = _comparison_universe(types=types, market_groups=market_groups)
    Instant.parse_iso(blueprints.received_at)
    for expiry in (blueprints.expires_at, blueprints.argus_expires_at):
        if expiry is not None:
            Instant.parse_iso(expiry)
    for item_id, row in blueprints.records.items():
        if (
            row.item_id != item_id
            or row.corporation_id != blueprints.corporation_id
            or row.response_metadata_id != blueprints.response_metadata_id
        ):
            raise ValueError(
                f"Blueprint item {item_id} does not belong to this snapshot."
            )
        classify_blueprint_quantity(row.quantity)
        if row.type_id not in types:
            raise ValueError(f"Missing static blueprint type {row.type_id}.")
    ids = collect_universe_name_ids(blueprints)
    successful: list[EsiResponse] = []
    for response in await fetch.universe_names(esi_link, schema, ids=ids):
        if isinstance(response, FailedEsiResponse):
            raise RuntimeError(
                "Universe-name lookup failed: "
                + "; ".join(
                    response.failed_response.error_messages,
                )
            )
        successful.append(response)
    if not successful:
        raise RuntimeError("Universe-name lookup returned no response batches.")
    names: dict[int, PostUniverseNamesDetail] = {}
    for record in validate.universe_names(successful).names:
        if record.id not in ids:
            continue
        if record.id in names and names[record.id] != record:
            raise ValueError(f"Conflicting universe names for ID {record.id}.")
        expected = (
            PostUniverseNamesCategory.CORPORATION
            if record.id == blueprints.corporation_id
            else PostUniverseNamesCategory.STATION
        )
        if record.category != expected:
            raise ValueError(f"Expected {expected.value} name for ID {record.id}.")
        names[record.id] = record
    corporation = names.get(blueprints.corporation_id)
    if corporation is None:
        raise ValueError(
            f"Missing corporation name for ID {blueprints.corporation_id}."
        )
    warnings: set[str] = set()
    rows: list[CorporationBlueprintReportRow] = []
    for row in sorted(blueprints.records.values(), key=lambda row: row.item_id):
        type_record = types[row.type_id]
        group = (
            market_groups[type_record.market_group_id]
            if type_record.market_group_id is not None
            else None
        )
        name = (
            names.get(row.location_id)
            if 60_000_000 <= row.location_id < 64_000_000
            else None
        )
        if name is None:
            warnings.add(
                f"Location {row.location_id}: UNKNOWN; private or unresolved location."
            )
        kind, count = classify_blueprint_quantity(row.quantity)
        rows.append(
            CorporationBlueprintReportRow(
                **asdict(row),
                type_name=type_record.name,
                published=type_record.published,
                market_group_id=type_record.market_group_id,
                market_path=group.str_path if group else None,
                location_name=name.name if name else "UNKNOWN",
                blueprint_kind=kind,
                item_count=count,
            )
        )
    inventory = tuple(rows)
    summaries = _summarize_originals(inventory, eligible=eligible)
    missing: list[MissingBpoRow] = []
    for type_id in eligible - {row.type_id for row in summaries}:
        type_record = types[type_id]
        group_id = type_record.market_group_id
        if group_id is None:
            raise ValueError(f"Eligible blueprint type {type_id} has no market group.")
        missing.append(
            MissingBpoRow(
                type_id=type_id,
                name=type_record.name,
                market_group_id=group_id,
                market_path=market_groups[group_id].str_path,
                base_price=type_record.base_price,
            )
        )
    expiry = blueprints.argus_expires_at or blueprints.expires_at
    for warning in sorted(warnings):
        logger.warning("%s", warning)
    return CorporationBlueprintsReport(
        corporation_id=blueprints.corporation_id,
        corporation_name=corporation.name,
        response_metadata_id=blueprints.response_metadata_id,
        received_at=blueprints.received_at,
        expires_at=blueprints.expires_at,
        argus_expires_at=blueprints.argus_expires_at,
        generated_at=generated_at.format_iso(),
        is_stale=Instant.parse_iso(expiry) <= generated_at
        if expiry is not None
        else None,
        inventory=inventory,
        owned_bpos=summaries,
        missing_bpos=tuple(
            sorted(missing, key=lambda row: (row.market_path, row.name, row.type_id))
        ),
        warnings=tuple(sorted(warnings)),
    )
