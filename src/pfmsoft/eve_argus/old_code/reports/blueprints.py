from dataclasses import dataclass

from eve_static_data.models import yaml_records as YR
from eve_static_data.models.common import Lang

from esi_link.argus.helpers.sde_lookups import (
    CollectedMarketPaths,
)
from esi_link.argus.models.esi_models import GetCorporationsCorporationIdBlueprints


def missing_blueprints(
    owned_blueprints: set[int],
    blueprints: dict[int, YR.Blueprints],
) -> frozenset[int]:
    """Returns a set of missing blueprint type IDs."""
    blueprint_type_ids = {bp.blueprintTypeID for bp in blueprints.values()}
    missing = blueprint_type_ids - owned_blueprints
    return frozenset(missing)


@dataclass
class BlueprintReport:
    type_id: int
    market_path: str
    name: str
    bpc: int = 0
    bpc_runs: int = 0
    bpo: int = 0
    bpc_me: int = 0
    bpc_te: int = 0
    bpo_me: int = 0
    bpo_te: int = 0


# TODO Make sure owned blueprint report includes invented bps.


def owned_blueprints_report_corporation(
    corporation_blueprints: GetCorporationsCorporationIdBlueprints,
    eve_types: dict[int, YR.EveTypes],
    market_paths: CollectedMarketPaths,
    lang: Lang = "en",
) -> dict[int, BlueprintReport]:
    """Returns a mapping of owned corporation blueprint type IDs to their market path and name."""
    reports: dict[int, BlueprintReport] = {}
    for bp_type_id, bps in corporation_blueprints.blueprints.items():
        eve_type = eve_types.get(bp_type_id)
        if eve_type is None:
            raise ValueError(f"Type ID {bp_type_id} not found in EVE types dataset.")
        name = eve_type.localized_name(lang) if eve_type else "Unknown type"
        if eve_type and eve_type.marketGroupID:
            market_path_record = market_paths.get(eve_type.marketGroupID)
            if market_path_record is None:
                raise ValueError(
                    f"Market group ID {eve_type.marketGroupID} not found in market paths dataset."
                )
            market_path = market_path_record.delimited_str_path()
        else:
            market_path = "UNKNOWN MARKET PATH"
        bpc = 0
        bpc_runs = 0
        bpo = 0
        bpc_me = 0
        bpc_te = 0
        bpo_me = 0
        bpo_te = 0
        for blueprint in bps:
            if blueprint.quantity == -2:  # BPC
                bpc_runs += blueprint.runs if blueprint.runs else 0
                bpc += 1
                # record the highest ME and TE for the BPC.
                bpc_me = max(bpc_me, blueprint.material_efficiency)
                bpc_te = max(bpc_te, blueprint.time_efficiency)
            elif blueprint.quantity == -1:  # BPO
                bpo += 1
                # record the highest ME and TE for the BPO.
                bpo_me = max(bpo_me, blueprint.material_efficiency)
                bpo_te = max(bpo_te, blueprint.time_efficiency)
            elif blueprint.quantity > 0:  # stack of unused BPOs
                bpo += blueprint.quantity
            else:
                raise ValueError(
                    f"Unexpected blueprint quantity {blueprint.quantity} for type ID {bp_type_id}."
                )
        report = BlueprintReport(
            type_id=bp_type_id,
            market_path=market_path,
            name=name,
            bpc=bpc,
            bpc_runs=bpc_runs,
            bpo=bpo,
            bpc_me=bpc_me,
            bpc_te=bpc_te,
            bpo_me=bpo_me,
            bpo_te=bpo_te,
        )
        reports[bp_type_id] = report
    # sort by market path, then name
    reports = dict(sorted(reports.items(), key=lambda x: (x[1].market_path, x[1].name)))
    return reports
