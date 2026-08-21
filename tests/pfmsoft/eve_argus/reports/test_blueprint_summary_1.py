"""Tests for the blueprint summary 1 report."""

from pfmsoft.eve_argus.models.esd import esd_datasets
from pfmsoft.eve_argus.models.esi import esi_argus
from pfmsoft.eve_argus.models.types import LanguageEnum
from pfmsoft.eve_argus.reports.blueprint_summary_1 import (
    generate_blueprint_summary_1_report,
)


def test_generate_blueprint_summary_1_report_builds_and_sorts_rows():
    """The report joins blueprint types and sorts rows by path then name."""
    blueprints = esd_datasets.BlueprintsDataset(
        dataset={
            200: esd_datasets.BlueprintRecord(
                blueprintTypeID=200,
                activities=esd_datasets.BlueprintActivities(),
            ),
            100: esd_datasets.BlueprintRecord(
                blueprintTypeID=100,
                activities=esd_datasets.BlueprintActivities(),
            ),
        }
    )
    types = esd_datasets.TypesDataset(
        dataset={
            200: esd_datasets.TypesRecord(
                groupID=1,
                marketGroupID=20,
                metaGroupID=2,
                metaLevel=5,
                name=esd_datasets.LocalizedString(en="Zulu", de="Zeta"),
                portionSize=1,
                published=True,
                techLevel=2,
                basePrice=125.5,
            ),
            100: esd_datasets.TypesRecord(
                groupID=1,
                name=esd_datasets.LocalizedString(en="Alpha", de="Alfa"),
                portionSize=10,
                published=False,
            ),
        }
    )
    meta_groups = esd_datasets.MetaGroupsDataset(
        dataset={
            2: esd_datasets.MetaGroupsRecord(
                name=esd_datasets.LocalizedString(en="Tech II", de="Tech II DE")
            )
        }
    )
    market_groups = esi_argus.MarketGroupsDataset(
        dataset={
            20: esi_argus.MarketGroup(
                received_at="2024-01-01T00:00:00Z",
                expires_at=None,
                market_group_id=20,
                name="Frigates",
                description="Frigates",
                path_str=("Ships", "Frigates"),
            )
        }
    )

    result = generate_blueprint_summary_1_report(
        blueprints=blueprints,
        market_groups=market_groups,
        meta_groups=meta_groups,
        types=types,
        language=LanguageEnum.DE,
    )

    assert result == [
        {
            "blueprint_type_id": 100,
            "name": "Alfa",
            "market_path": "",
            "meta_group_id": None,
            "meta_group_name": None,
            "tech_level": None,
            "meta_level": None,
            "base_price": None,
            "portion_size": 10,
            "published": False,
        },
        {
            "blueprint_type_id": 200,
            "name": "Zeta",
            "market_path": "Ships > Frigates",
            "meta_group_id": 2,
            "meta_group_name": "Tech II DE",
            "tech_level": 2,
            "meta_level": 5,
            "base_price": 125.5,
            "portion_size": 1,
            "published": True,
        },
    ]


def test_generate_blueprint_summary_1_report_skips_missing_type():
    """Blueprints without a corresponding type record cannot form a report row."""
    blueprints = esd_datasets.BlueprintsDataset(
        dataset={
            100: esd_datasets.BlueprintRecord(
                blueprintTypeID=100,
                activities=esd_datasets.BlueprintActivities(),
            )
        }
    )

    result = generate_blueprint_summary_1_report(
        blueprints=blueprints,
        market_groups=esi_argus.MarketGroupsDataset(dataset={}),
        meta_groups=esd_datasets.MetaGroupsDataset(dataset={}),
        types=esd_datasets.TypesDataset(dataset={}),
    )

    assert result == []
