"""Proof script for the corporation blueprints ESI response.

Loads the corporation blueprints (an authorized endpoint requiring the Director
role) from ESI, then builds an owned-vs-missing BPO report against the published
blueprints available on the market. Requires sample auth data from the dev secrets
directory; the script exits without loading data if none is available.
"""

import asyncio
from logging import getLogger
from time import perf_counter_ns
from uuid import UUID

from _shared import (
    PROOF_OUTPUT_DIR,
    create_resources,
    get_sample_auth_data,
    setup_logging,
)

from pfmsoft.eve_argus.data_loaders.esd_datasets import EsdDatasetsLoader
from pfmsoft.eve_argus.data_loaders.esi_responses import EsiResponseLoader
from pfmsoft.eve_argus.data_transform.market_groups import transform_market_groups
from pfmsoft.eve_argus.models.esi import esi_response_models
from pfmsoft.eve_argus.reports.corp_missing_bpo import (
    CorpBpoReport,
    CorpBpoReportRoot,
    collect_bpo_type_ids,
    generate_corp_missing_bpo_report,
)
from pfmsoft.eve_argus.reports.corp_missing_bpo_markdown import (
    render_corp_bpo_report_markdown,
)

logger = getLogger(__name__)

CORPORATION_BLUEPRINTS_FILENAME = (
    PROOF_OUTPUT_DIR / "corporation_blueprints_response.json"
)
CORPORATION_BPO_REPORT_FILENAME = PROOF_OUTPUT_DIR / "corporation_bpo_report.md"
CORPORATION_BPO_REPORT_JSON_FILENAME = PROOF_OUTPUT_DIR / "corporation_bpo_report.json"


async def prove_corporation_blueprints() -> None:
    """Prove loading corporation blueprints and building the owned-vs-missing report."""
    sample_auth_data = get_sample_auth_data()
    print(f"Using sample auth data: {sample_auth_data}")
    if sample_auth_data is None:
        print("No sample auth data available, skipping corporation blueprints.")
        return

    async with create_resources() as resources:
        loader = EsiResponseLoader(
            esi_link=resources.esi_link, schema=resources.esi_schema
        )
        esd_loader = EsdDatasetsLoader(resources.sd_query_manager)
        blueprints_response = await corporation_blueprints(
            loader=loader,
            corporation_id=sample_auth_data["corporation_id"],
            character_id=sample_auth_data["character_id"],
            credential_id=sample_auth_data["cred_id"],
        )
        _ = await corporation_bpo_report(
            loader=loader,
            esd_loader=esd_loader,
            blueprints_response=blueprints_response,
        )


async def corporation_blueprints(
    loader: EsiResponseLoader,
    corporation_id: int,
    character_id: int,
    credential_id: UUID,
) -> esi_response_models.GetCorporationsCorporationIdBlueprintsResponse:
    """Loads the corporation blueprints from ESI."""
    print()
    start_time = perf_counter_ns()
    corporation_blueprints_response = await loader.corporation_blueprints(
        corporation_id=corporation_id,
        character_id=character_id,
        credential_id=credential_id,
    )
    end_time = perf_counter_ns()
    filename = CORPORATION_BLUEPRINTS_FILENAME
    filename.write_text(corporation_blueprints_response.serialize(indent=2))
    print(f"Saved corporation blueprints response to {filename}")
    print(
        f"Time taken to load corporation blueprints: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
    )
    print(
        f"Loaded {len(corporation_blueprints_response.response_data.blueprints)} corporation blueprints."
    )
    return corporation_blueprints_response


async def corporation_bpo_report(
    loader: EsiResponseLoader,
    esd_loader: EsdDatasetsLoader,
    blueprints_response: esi_response_models.GetCorporationsCorporationIdBlueprintsResponse,
) -> CorpBpoReport:
    """Builds and renders the owned-vs-missing BPO report for the corporation."""
    print()
    start_time = perf_counter_ns()
    market_group_ids = await loader.market_group_ids()
    market_groups_details = await loader.market_groups_details(
        set(market_group_ids.response_data.market_group_ids)
    )
    market_groups = transform_market_groups(market_groups_details.response_data)
    published_type_ids = esd_loader.published_types()

    type_ids = collect_bpo_type_ids(
        blueprints_response.response_data, market_groups, published_type_ids
    )
    names_response = await loader.universe_names(type_ids)
    names = {name.id: name.name for name in names_response.response_data.names}
    base_prices = {
        type_id: record.basePrice
        for type_id, record in esd_loader.types().dataset.items()
    }

    report = generate_corp_missing_bpo_report(
        blueprints_response.response_data,
        market_groups,
        published_type_ids,
        names=names,
        base_prices=base_prices,
    )
    end_time = perf_counter_ns()

    CORPORATION_BPO_REPORT_JSON_FILENAME.write_text(
        CorpBpoReportRoot(report).model_dump_json(indent=2)
    )
    print(
        f"Saved corporation BPO report data to {CORPORATION_BPO_REPORT_JSON_FILENAME}"
    )
    CORPORATION_BPO_REPORT_FILENAME.write_text(render_corp_bpo_report_markdown(report))
    print(f"Saved corporation BPO report to {CORPORATION_BPO_REPORT_FILENAME}")
    print(
        f"Time taken to build corporation BPO report: {(end_time - start_time) / 1_000_000_000:.6f} seconds"
    )
    print(
        f"Report: {len(report.owned)} owned, {len(report.missing)} missing blueprint originals."
    )
    return report


if __name__ == "__main__":
    log_filepath = setup_logging("corporation-blueprints")
    logger.info(f"Logging to {log_filepath}")
    asyncio.run(prove_corporation_blueprints())
