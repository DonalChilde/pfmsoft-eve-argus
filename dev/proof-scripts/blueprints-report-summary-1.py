"""Generate the blueprint summary 1 report as a CSV proof output."""

import asyncio
import csv
from pathlib import Path

from pfmsoft.eve_argus.data_loaders.esd_datasets import EsdDatasetsLoader
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.models.esd import esd_datasets
from pfmsoft.eve_argus.models.esi import argus_response_models
from pfmsoft.eve_argus.reports.blueprint_summary_1 import (
    BlueprintSummary1Report,
    generate_blueprint_summary_1_report,
)
from pfmsoft.eve_argus.settings import get_settings

PROOF_OUTPUT_DIR = Path(__file__).parent / "proof-output"
MARKET_GROUPS_TRANSFORMED_FILENAME = PROOF_OUTPUT_DIR / "market_groups_transformed.json"
BLUEPRINTS_REPORT_SUMMARY_1_FILENAME = (
    PROOF_OUTPUT_DIR / "blueprints_report_summary_1.csv"
)
REPORT_FIELDNAMES = tuple(BlueprintSummary1Report.__annotations__)


def load_market_groups() -> argus_response_models.MarketGroupsDataset:
    """Load transformed market groups from the existing proof output."""
    return argus_response_models.MarketGroupsDataset.deserialize(
        MARKET_GROUPS_TRANSFORMED_FILENAME.read_text()
    )


def write_report_csv(report: list[BlueprintSummary1Report], filename: Path) -> None:
    """Write blueprint summary report rows to a CSV file."""
    with filename.open("w", newline="", encoding="utf-8") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=REPORT_FIELDNAMES)
        writer.writeheader()
        writer.writerows(report)


async def generate_blueprint_report() -> None:
    """Load source data, generate the report, and write its CSV output."""
    market_groups = load_market_groups()
    settings = get_settings()
    resource_manager = EveArgusResources(settings=settings)

    async with resource_manager as resources:
        esd_loader = EsdDatasetsLoader(resources.sd_query_manager)
        blueprints: esd_datasets.BlueprintsDataset = esd_loader.blueprints()
        meta_groups: esd_datasets.MetaGroupsDataset = esd_loader.meta_groups()
        types: esd_datasets.TypesDataset = esd_loader.types()

    report = generate_blueprint_summary_1_report(
        blueprints=blueprints,
        market_groups=market_groups,
        meta_groups=meta_groups,
        types=types,
    )
    write_report_csv(report, BLUEPRINTS_REPORT_SUMMARY_1_FILENAME)
    print(
        f"Wrote {len(report)} blueprint summary rows to "
        f"{BLUEPRINTS_REPORT_SUMMARY_1_FILENAME}"
    )


if __name__ == "__main__":
    asyncio.run(generate_blueprint_report())
