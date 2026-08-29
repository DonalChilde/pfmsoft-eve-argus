"""Generate the blueprint summary 1 report."""

from typing import TypedDict

from pfmsoft.eve_argus.models.esd import esd_datasets
from pfmsoft.eve_argus.models.esi import esi_argus
from pfmsoft.eve_argus.models.types import LanguageEnum


class BlueprintSummary1Report(TypedDict):
    """Report for blueprint summary 1."""

    blueprint_type_id: int
    name: str
    market_path: str
    meta_group_id: int | None
    meta_group_name: str | None
    base_price: float | None
    portion_size: int
    published: bool


def generate_blueprint_summary_1_report(
    blueprints: esd_datasets.BlueprintsDataset,
    market_groups: esi_argus.MarketGroupsDataset,
    meta_groups: esd_datasets.MetaGroupsDataset,
    types: esd_datasets.TypesDataset,
    language: LanguageEnum = LanguageEnum.EN,
) -> list[BlueprintSummary1Report]:
    """Generate the blueprint summary 1 report.

    Returns:
        list[BlueprintSummary1Report]: The generated report.
    """
    # generate the list of dicts, when done sort by market_path and name
    report: list[BlueprintSummary1Report] = []
    for blueprint in blueprints.dataset.values():
        blueprint_type_id = blueprint.blueprintTypeID
        type_record = types.dataset.get(blueprint_type_id)
        if type_record is None:
            continue
        if type_record.marketGroupID is None:
            market_group = None
        else:
            market_group = market_groups.dataset.get(type_record.marketGroupID)
        market_path = " > ".join(market_group.path_str) if market_group else ""

        meta_group_id = type_record.metaGroupID
        meta_group = (
            meta_groups.dataset.get(meta_group_id)
            if meta_group_id is not None
            else None
        )
        # portion size is 1 for blueprints, so we want to use the portion size of the product type instead
        # products are from either the manufacturing or reaction activity, but not both.
        # blueprints will not always have a manufacturing or reaction activity, so we need to check for that as well.
        portion_size = -1
        if (
            blueprint.activities.manufacturing is not None
            and blueprint.activities.reaction is not None
        ):
            print(
                f"Warning: blueprint {blueprint_type_id} has both manufacturing and reaction activities."
            )
        if blueprint.activities.manufacturing is not None:
            if blueprint.activities.manufacturing.products:
                product_type_id = blueprint.activities.manufacturing.products[0].typeID
                if len(blueprint.activities.manufacturing.products) > 1:
                    print(
                        f"Warning: blueprint {blueprint_type_id} has more than one manufacturing product, using the first one."
                    )
                product_type = types.dataset.get(product_type_id)
                if product_type is not None:
                    portion_size = product_type.portionSize
        elif blueprint.activities.reaction is not None:
            if blueprint.activities.reaction.products:
                product_type_id = blueprint.activities.reaction.products[0].typeID
                if len(blueprint.activities.reaction.products) > 1:
                    print(
                        f"Warning: blueprint {blueprint_type_id} has more than one reaction product, using the first one."
                    )
                product_type = types.dataset.get(product_type_id)
                if product_type is not None:
                    portion_size = product_type.portionSize

        report.append({
            "blueprint_type_id": blueprint_type_id,
            "name": type_record.name_localized(language),
            "market_path": market_path,
            "meta_group_id": meta_group_id,
            "meta_group_name": (
                meta_group.name_localized(language) if meta_group else None
            ),
            "base_price": type_record.basePrice,
            "portion_size": portion_size,
            "published": type_record.published,
        })

    report.sort(key=lambda item: (item["market_path"], item["name"]))
    return report
