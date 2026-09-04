"""Report data to identify missing BPO blueprints in a corporation's inventory.

A BPO blueprint is considered missing if it is available on the market but not in the
corporation's inventory. The report lists all owned blueprints, with market path string,
quantity for each, and the highest ME/TE available in an "owned" table. The missing table
lists all BPO blueprints that are available on the market but not owned by the
corporation, including their market path string and base price. Only published
blueprints are considered, based on published type_ids (e.g. get all blueprint type_ids
from market groups, then filter for only published type_ids).
"""

from dataclasses import dataclass, field

from pydantic import RootModel

from pfmsoft.eve_argus.helpers.market_path_filters import filter_type_ids_by_market_path
from pfmsoft.eve_argus.models.esi.argus_response_models import MarketGroup
from pfmsoft.eve_argus.models.esi.esi_response_models import (
    GetCorporationsCorporationIdBlueprints,
    GetCorporationsCorporationIdBlueprintsDetail,
)

BLUEPRINTS_MARKET_GROUP = 2

NOT_FOUND = "Unknown"


@dataclass(slots=True, kw_only=True)
class OwnedBpoRow:
    """One owned blueprint original/stack, aggregated by type."""

    type_id: int
    name: str
    market_path: str
    quantity: int
    material_efficiency: int
    time_efficiency: int


@dataclass(slots=True, kw_only=True)
class MissingBpoRow:
    """One published market blueprint not owned by the corporation."""

    type_id: int
    name: str
    market_path: str
    base_price: float | None


@dataclass(slots=True, kw_only=True)
class CorpBpoReport:
    """Owned and missing blueprint originals for a corporation."""

    corporation_id: int
    owned: list[OwnedBpoRow] = field(default_factory=list[OwnedBpoRow])
    missing: list[MissingBpoRow] = field(default_factory=list[MissingBpoRow])


CorpBpoReportRoot = RootModel[CorpBpoReport]


def _market_blueprint_type_ids(
    market_groups: dict[int, MarketGroup], published_type_ids: set[int]
) -> set[int]:
    """Published type IDs under the blueprints market group."""
    market_type_ids = filter_type_ids_by_market_path(
        market_groups, include={BLUEPRINTS_MARKET_GROUP}
    )
    return market_type_ids & published_type_ids


def _type_market_paths(market_groups: dict[int, MarketGroup]) -> dict[int, str]:
    """Reverse-map each type ID to its market group's joined path string."""
    paths: dict[int, str] = {}
    for group in market_groups.values():
        path = " > ".join(group.path_str)
        for type_id in group.types:
            paths[type_id] = path
    return paths


def collect_bpo_type_ids(
    blueprints: GetCorporationsCorporationIdBlueprints,
    market_groups: dict[int, MarketGroup],
    published_type_ids: set[int],
) -> set[int]:
    """Collect the type IDs that need name resolution for the report.

    This is the union of the corporation's owned blueprint type IDs and the published
    blueprint type IDs available on the market. Names for these IDs are resolved
    separately (e.g. via a PostUniverseNames call) and passed to
    :func:`generate_corp_missing_bpo_report`.

    Args:
        blueprints: The corporation blueprints response.
        market_groups: Transformed market groups keyed by market group ID.
        published_type_ids: The set of published type IDs.

    Returns:
        The set of type IDs to resolve to names.
    """
    owned_type_ids = {detail.type_id for detail in blueprints.blueprints}
    return owned_type_ids | _market_blueprint_type_ids(
        market_groups, published_type_ids
    )


def _best_owned_stack(
    stacks: list[GetCorporationsCorporationIdBlueprintsDetail],
) -> GetCorporationsCorporationIdBlueprintsDetail:
    """Choose the stack with the highest ME, breaking ties by highest TE then quantity."""
    return max(
        stacks,
        key=lambda s: (s.material_efficiency, s.time_efficiency, s.quantity),
    )


def _original_count(stack: GetCorporationsCorporationIdBlueprintsDetail) -> int:
    """Count the number of originals in an owned stack.

    A ``quantity`` of -1 is a single original; a positive quantity is a stack of that
    many originals. (Copies, quantity -2, are filtered out before this is called.)
    """
    return 1 if stack.quantity == -1 else stack.quantity


def generate_corp_missing_bpo_report(
    blueprints: GetCorporationsCorporationIdBlueprints,
    market_groups: dict[int, MarketGroup],
    published_type_ids: set[int],
    *,
    names: dict[int, str],
    base_prices: dict[int, float | None],
) -> CorpBpoReport:
    """Generate the owned-vs-missing BPO report for a corporation.

    A blueprint stack counts as owned when its ``quantity`` is not -2 (i.e. it is an
    original or an unprocessed stack, not a copy). Owned stacks are aggregated to one
    row per type, showing the highest material efficiency available (ties broken by the
    highest time efficiency at that level) and the total quantity across stacks.

    Missing rows are the published blueprint type IDs available on the market that the
    corporation does not own.

    Names and base prices are injected so their sources can change independently of this
    module.

    Args:
        blueprints: The corporation blueprints response.
        market_groups: Transformed market groups keyed by market group ID.
        published_type_ids: The set of published type IDs.
        names: Mapping of type ID to blueprint name.
        base_prices: Mapping of type ID to base price (may be None for a type).

    Returns:
        The generated report.
    """
    market_type_ids = _market_blueprint_type_ids(market_groups, published_type_ids)
    paths = _type_market_paths(market_groups)

    owned_by_type: dict[int, list[GetCorporationsCorporationIdBlueprintsDetail]] = {}
    for detail in blueprints.blueprints:
        if detail.quantity == -2:
            continue  # a copy, not an original
        if detail.type_id not in market_type_ids:
            continue  # not a published market blueprint
        owned_by_type.setdefault(detail.type_id, []).append(detail)

    owned_rows = [
        OwnedBpoRow(
            type_id=type_id,
            name=names.get(type_id, NOT_FOUND),
            market_path=paths.get(type_id, ""),
            quantity=sum(_original_count(stack) for stack in stacks),
            material_efficiency=_best_owned_stack(stacks).material_efficiency,
            time_efficiency=_best_owned_stack(stacks).time_efficiency,
        )
        for type_id, stacks in owned_by_type.items()
    ]
    owned_rows.sort(key=lambda row: (row.market_path, row.name))

    missing_type_ids = market_type_ids - set(owned_by_type)
    missing_rows = [
        MissingBpoRow(
            type_id=type_id,
            name=names.get(type_id, NOT_FOUND),
            market_path=paths.get(type_id, ""),
            base_price=base_prices.get(type_id),
        )
        for type_id in missing_type_ids
    ]
    missing_rows.sort(key=lambda row: (row.market_path, row.name))

    return CorpBpoReport(
        corporation_id=blueprints.corporation_id,
        owned=owned_rows,
        missing=missing_rows,
    )


__all__ = [
    "BLUEPRINTS_MARKET_GROUP",
    "CorpBpoReport",
    "CorpBpoReportRoot",
    "MissingBpoRow",
    "OwnedBpoRow",
    "collect_bpo_type_ids",
    "generate_corp_missing_bpo_report",
]
