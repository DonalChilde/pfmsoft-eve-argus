"""Inspect static data relevant to the reprocessing prototype."""

import asyncio
import json
from pathlib import Path
from typing import Any

from pfmsoft.eve_argus.data_loaders.esd_datasets import EsdDatasetsLoader
from pfmsoft.eve_argus.eve_argus import EveArgusResources
from pfmsoft.eve_argus.settings import get_settings

PROOF_OUTPUT_DIR = Path(__file__).parent.parent / "proof-output" / "reprocessing"
REPORT_FILENAME = PROOF_OUTPUT_DIR / "static_inventory.json"
SAMPLE_LIMIT = 25


def build_inventory(
    types: dict[int, Any], type_materials: dict[int, Any]
) -> dict[str, Any]:
    """Build a diagnostic inventory from loaded ESD datasets."""
    eligible_types = {
        type_id: record
        for type_id, record in types.items()
        if record.marketGroupID is not None
    }
    eligible_material_types = eligible_types

    missing_material_records: list[dict[str, Any]] = []
    randomized_inputs: list[dict[str, Any]] = []
    unclassified_components: list[dict[str, Any]] = []
    inputs_with_materials = 0

    for input_type_id, input_record in eligible_types.items():
        material_record = type_materials.get(input_type_id)
        if material_record is None:
            missing_material_records.append({
                "type_id": input_type_id,
                "name": input_record.name_localized(),
            })
            continue

        materials = material_record.materials or []
        if materials:
            inputs_with_materials += 1

        randomized_materials = material_record.randomizedMaterials or []
        if randomized_materials:
            randomized_inputs.append({
                "type_id": input_type_id,
                "name": input_record.name_localized(),
                "material_count": len(materials),
                "randomized_material_count": len(randomized_materials),
            })

        for material in materials:
            material_type = eligible_material_types.get(material.materialTypeID)
            if material_type is None:
                unclassified_components.append({
                    "input_type_id": input_type_id,
                    "input_name": input_record.name_localized(),
                    "material_type_id": material.materialTypeID,
                    "quantity": material.quantity,
                })

    return {
        "published_type_count": len(types),
        "published_market_group_type_count": len(eligible_types),
        "eligible_inputs_with_materials_count": inputs_with_materials,
        "eligible_inputs_without_material_records_count": len(missing_material_records),
        "randomized_input_count": len(randomized_inputs),
        "unclassified_component_count": len(unclassified_components),
        "missing_material_records_sample": missing_material_records[:SAMPLE_LIMIT],
        "randomized_inputs": randomized_inputs[:SAMPLE_LIMIT],
        "unclassified_components_sample": unclassified_components[:SAMPLE_LIMIT],
    }


async def inspect_static_data() -> None:
    """Load static datasets and write the reprocessing inventory."""
    settings = get_settings()
    resource_manager = EveArgusResources(settings=settings)

    async with resource_manager as resources:
        esd_loader = EsdDatasetsLoader(resources.sd_query_manager)
        types_dataset = esd_loader.types(published=True)
        type_materials_dataset = esd_loader.type_materials()

    inventory = build_inventory(
        types=types_dataset.dataset,
        type_materials=type_materials_dataset.dataset,
    )
    PROOF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_FILENAME.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(inventory, indent=2))
    print(f"Wrote static inventory to {REPORT_FILENAME}")


if __name__ == "__main__":
    asyncio.run(inspect_static_data())
