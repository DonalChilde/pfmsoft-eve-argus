"""Tests for the corporation owned-vs-missing BPO report generation."""

from pfmsoft.eve_argus.models.esi.argus_response_models import MarketGroup
from pfmsoft.eve_argus.models.esi.esi_response_models import (
    GetCorporationsCorporationIdBlueprints,
    GetCorporationsCorporationIdBlueprintsDetail,
    GetCorporationsCorporationIdBlueprintsDetail_LocationFlag,
)
from pfmsoft.eve_argus.reports.corp_missing_bpo import (
    BLUEPRINTS_MARKET_GROUP,
    collect_bpo_type_ids,
    generate_corp_missing_bpo_report,
)

RECEIVED_AT = "2026-09-04T00:00:00Z"

# Market group tree: root 2 (Blueprints) -> 10 (Ship Blueprints) -> 100 (Frigates).
# Type 1000 (owned) and 1001 (missing) live in group 100.
# Type 2000 lives in an unrelated group 999 (not under market group 2).
SHIP_FRIGATES = MarketGroup(
    received_at=RECEIVED_AT,
    expires_at=None,
    market_group_id=100,
    name="Frigate Blueprints",
    description="",
    parent_group_id=10,
    types=[1000, 1001],
    path_str=("Blueprints", "Ship Blueprints", "Frigate Blueprints"),
    path_int=(BLUEPRINTS_MARKET_GROUP, 10, 100),
)
SHIP_BLUEPRINTS = MarketGroup(
    received_at=RECEIVED_AT,
    expires_at=None,
    market_group_id=10,
    name="Ship Blueprints",
    description="",
    parent_group_id=BLUEPRINTS_MARKET_GROUP,
    types=[],
    path_str=("Blueprints", "Ship Blueprints"),
    path_int=(BLUEPRINTS_MARKET_GROUP, 10),
)
BLUEPRINTS_ROOT = MarketGroup(
    received_at=RECEIVED_AT,
    expires_at=None,
    market_group_id=BLUEPRINTS_MARKET_GROUP,
    name="Blueprints",
    description="",
    parent_group_id=None,
    types=[],
    path_str=("Blueprints",),
    path_int=(BLUEPRINTS_MARKET_GROUP,),
)
UNRELATED = MarketGroup(
    received_at=RECEIVED_AT,
    expires_at=None,
    market_group_id=999,
    name="Ammo",
    description="",
    parent_group_id=None,
    types=[2000],
    path_str=("Ammo",),
    path_int=(999,),
)


def make_market_groups() -> dict[int, MarketGroup]:
    """Build the market group fixture tree."""
    return {
        group.market_group_id: group
        for group in (SHIP_FRIGATES, SHIP_BLUEPRINTS, BLUEPRINTS_ROOT, UNRELATED)
    }


def make_blueprint(
    type_id: int,
    *,
    quantity: int,
    material_efficiency: int = 0,
    time_efficiency: int = 0,
    item_id: int | None = None,
) -> GetCorporationsCorporationIdBlueprintsDetail:
    """Build a blueprint detail with sensible defaults."""
    return GetCorporationsCorporationIdBlueprintsDetail(
        item_id=item_id if item_id is not None else type_id * 100,
        type_id=type_id,
        location_id=60014719,
        location_flag=GetCorporationsCorporationIdBlueprintsDetail_LocationFlag.CORP_SAG_1,
        quantity=quantity,
        time_efficiency=time_efficiency,
        material_efficiency=material_efficiency,
        runs=-1,
    )


def make_blueprints_response(
    details: list[GetCorporationsCorporationIdBlueprintsDetail],
) -> GetCorporationsCorporationIdBlueprints:
    """Wrap blueprint details in a response model."""
    return GetCorporationsCorporationIdBlueprints(
        received_at=RECEIVED_AT,
        expires_at=None,
        corporation_id=98777771,
        blueprints=details,
    )


def make_names() -> dict[int, str]:
    """Names for the resolvable type ids."""
    return {1000: "Vexor Blueprint", 1001: "Rifter Blueprint"}


def make_base_prices() -> dict[int, float | None]:
    """Base prices for the resolvable type ids."""
    return {1000: 1500000.0, 1001: 250000.0}


def test_owned_excludes_copies_and_includes_originals_and_stacks() -> None:
    """Copies (quantity -2) are excluded; originals (-1) and stacks (positive) count."""
    response = make_blueprints_response([
        make_blueprint(1000, quantity=-1),  # original -> owned
        make_blueprint(1000, quantity=-2, item_id=999),  # copy -> excluded
    ])
    report = generate_corp_missing_bpo_report(
        response,
        make_market_groups(),
        {1000, 1001},
        names=make_names(),
        base_prices=make_base_prices(),
    )

    owned = {row.type_id: row for row in report.owned}
    assert 1000 in owned
    # Only the original stack counted toward quantity, not the copy.
    assert owned[1000].quantity == 1


def test_owned_aggregates_max_me_then_max_te() -> None:
    """Per type, the highest ME wins, with ties broken by the highest TE at that ME."""
    response = make_blueprints_response([
        make_blueprint(1000, quantity=-1, material_efficiency=10, time_efficiency=5),
        make_blueprint(
            1000, quantity=-1, material_efficiency=10, time_efficiency=18, item_id=1
        ),
        make_blueprint(
            1000, quantity=-1, material_efficiency=2, time_efficiency=20, item_id=2
        ),
        make_blueprint(
            1000, quantity=-1, material_efficiency=0, time_efficiency=0, item_id=3
        ),
    ])
    report = generate_corp_missing_bpo_report(
        response,
        make_market_groups(),
        {1000, 1001},
        names=make_names(),
        base_prices=make_base_prices(),
    )

    owned = {row.type_id: row for row in report.owned}
    assert owned[1000].material_efficiency == 10
    assert owned[1000].time_efficiency == 18
    # Quantity summed across all four owned stacks.
    assert owned[1000].quantity == 4


def test_owned_uses_name_and_market_path_from_lookups() -> None:
    """Owned rows carry the resolved name and the reverse-mapped market path."""
    response = make_blueprints_response([make_blueprint(1000, quantity=-1)])
    report = generate_corp_missing_bpo_report(
        response,
        make_market_groups(),
        {1000, 1001},
        names=make_names(),
        base_prices=make_base_prices(),
    )

    row = report.owned[0]
    assert row.name == "Vexor Blueprint"
    assert row.market_path == "Blueprints > Ship Blueprints > Frigate Blueprints"


def test_missing_lists_unowned_published_bpos_with_base_price() -> None:
    """Missing rows are published market BPOs not owned, with base price and path."""
    response = make_blueprints_response([make_blueprint(1000, quantity=-1)])
    report = generate_corp_missing_bpo_report(
        response,
        make_market_groups(),
        {1000, 1001},
        names=make_names(),
        base_prices=make_base_prices(),
    )

    missing = {row.type_id: row for row in report.missing}
    assert set(missing) == {1001}
    assert missing[1001].name == "Rifter Blueprint"
    assert missing[1001].base_price == 250000.0
    assert (
        missing[1001].market_path == "Blueprints > Ship Blueprints > Frigate Blueprints"
    )


def test_non_blueprint_market_types_are_excluded() -> None:
    """Types outside the blueprints market group are never reported missing."""
    response = make_blueprints_response([])
    report = generate_corp_missing_bpo_report(
        response,
        make_market_groups(),
        {1000, 1001, 2000},
        names=make_names(),
        base_prices=make_base_prices(),
    )

    missing_ids = {row.type_id for row in report.missing}
    assert 2000 not in missing_ids
    assert missing_ids == {1000, 1001}


def test_unpublished_types_are_excluded_from_missing() -> None:
    """A blueprint type not in published_type_ids is not reported missing."""
    response = make_blueprints_response([])
    report = generate_corp_missing_bpo_report(
        response,
        make_market_groups(),
        {1000},  # 1001 not published
        names=make_names(),
        base_prices=make_base_prices(),
    )

    assert {row.type_id for row in report.missing} == {1000}


def test_all_owned_produces_empty_missing() -> None:
    """When every published BPO is owned, the missing table is empty."""
    response = make_blueprints_response([
        make_blueprint(1000, quantity=-1),
        make_blueprint(1001, quantity=-1, item_id=100100),
    ])
    report = generate_corp_missing_bpo_report(
        response,
        make_market_groups(),
        {1000, 1001},
        names=make_names(),
        base_prices=make_base_prices(),
    )

    assert report.missing == []


def test_empty_corporation_reports_everything_missing() -> None:
    """With no owned blueprints, all published market BPOs are missing."""
    response = make_blueprints_response([])
    report = generate_corp_missing_bpo_report(
        response,
        make_market_groups(),
        {1000, 1001},
        names=make_names(),
        base_prices=make_base_prices(),
    )

    assert report.owned == []
    assert {row.type_id for row in report.missing} == {1000, 1001}


def test_rows_sorted_by_market_path_then_name() -> None:
    """Owned and missing rows sort by market path, then blueprint name."""
    response = make_blueprints_response([
        make_blueprint(1001, quantity=-1, item_id=100100),
        make_blueprint(1000, quantity=-1),
    ])
    report = generate_corp_missing_bpo_report(
        response,
        make_market_groups(),
        {1000, 1001},
        names=make_names(),
        base_prices=make_base_prices(),
    )

    names = [row.name for row in report.owned]
    assert names == sorted(names)


def test_collect_bpo_type_ids_unions_owned_and_market() -> None:
    """Collected IDs cover owned blueprint types and published market BPO types."""
    response = make_blueprints_response([make_blueprint(1000, quantity=-1)])
    ids = collect_bpo_type_ids(
        response,
        make_market_groups(),
        {1000, 1001},
    )

    assert ids == {1000, 1001}
