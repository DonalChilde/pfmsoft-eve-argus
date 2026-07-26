"""Functions to extract data from SDE datasets."""

import logging
from dataclasses import dataclass

from eve_static_data.models import yaml_records as YR
from eve_static_data.models.common import Lang

logger = logging.getLogger(__name__)

# FIXME these convenience functions could go in eve-static-data.


def manufactured_items_produced_by_blueprints(
    blueprints: dict[int, YR.Blueprints],
) -> frozenset[int]:
    """Returns a set of item type IDs that can be produced by blueprints."""
    manufactured_items: set[int] = set()
    for blueprint in blueprints.values():
        if blueprint.activities.manufacturing is not None:
            if blueprint.activities.manufacturing.products is not None:
                for product in blueprint.activities.manufacturing.products:
                    manufactured_items.add(product.typeID)
    return frozenset(manufactured_items)


def reaction_items_produced_by_blueprints(
    blueprints: dict[int, YR.Blueprints],
) -> frozenset[int]:
    """Returns a set of item type IDs that can be produced by reaction blueprints."""
    reaction_items: set[int] = set()
    for blueprint in blueprints.values():
        if blueprint.activities.reaction is not None:
            if blueprint.activities.reaction.products is not None:
                for product in blueprint.activities.reaction.products:
                    reaction_items.add(product.typeID)
    return frozenset(reaction_items)


def materials_used_in_copying(
    blueprints: dict[int, YR.Blueprints],
) -> frozenset[int]:
    """Returns a set of item type IDs that are used as materials in copying blueprints."""
    materials: set[int] = set()
    for blueprint in blueprints.values():
        if blueprint.activities.copying is not None:
            if blueprint.activities.copying.materials is not None:
                for material in blueprint.activities.copying.materials:
                    materials.add(material.typeID)
    return frozenset(materials)


def materials_used_in_invention(
    blueprints: dict[int, YR.Blueprints],
) -> frozenset[int]:
    """Returns a set of item type IDs that are used as materials in invention blueprints."""
    materials: set[int] = set()
    for blueprint in blueprints.values():
        if blueprint.activities.invention is not None:
            if blueprint.activities.invention.materials is not None:
                for material in blueprint.activities.invention.materials:
                    materials.add(material.typeID)
    return frozenset(materials)


def materials_used_in_researching_time_efficiency(
    blueprints: dict[int, YR.Blueprints],
) -> frozenset[int]:
    """Returns a set of item type IDs that are used as materials in researching time efficiency blueprints."""
    materials: set[int] = set()
    for blueprint in blueprints.values():
        if blueprint.activities.research_time is not None:
            if blueprint.activities.research_time.materials is not None:
                for material in blueprint.activities.research_time.materials:
                    materials.add(material.typeID)
    return frozenset(materials)


def materials_used_in_researching_material_efficiency(
    blueprints: dict[int, YR.Blueprints],
) -> frozenset[int]:
    """Returns a set of item type IDs that are used as materials in researching material efficiency blueprints."""
    materials: set[int] = set()
    for blueprint in blueprints.values():
        if blueprint.activities.research_material is not None:
            if blueprint.activities.research_material.materials is not None:
                for material in blueprint.activities.research_material.materials:
                    materials.add(material.typeID)
    return frozenset(materials)


def materials_used_in_reactions(
    blueprints: dict[int, YR.Blueprints], published_type_ids: set[int] | None
) -> frozenset[int]:
    """Returns a set of item type IDs that are used as materials in reaction blueprints."""
    materials: set[int] = set()
    for blueprint in blueprints.values():
        if blueprint.activities.reaction is not None:
            if blueprint.activities.reaction.materials is not None:
                for material in blueprint.activities.reaction.materials:
                    materials.add(material.typeID)
    return frozenset(materials)


def materials_used_in_manufacturing(
    blueprints: dict[int, YR.Blueprints], published_type_ids: set[int] | None
) -> frozenset[int]:
    """Returns a set of item type IDs that are used as materials in manufacturing blueprints."""
    materials: set[int] = set()
    for blueprint in blueprints.values():
        if blueprint.activities.manufacturing is not None:
            if blueprint.activities.manufacturing.materials is not None:
                for material in blueprint.activities.manufacturing.materials:
                    materials.add(material.typeID)
    return frozenset(materials)


def published_type_ids(
    eve_types: dict[int, YR.EveTypes],
) -> frozenset[int]:
    """Returns a set of item type IDs that are published."""
    published = {
        type_id for type_id, type_info in eve_types.items() if type_info.published
    }
    return frozenset(published)


def types_in_market(
    eve_types: dict[int, YR.EveTypes],
) -> frozenset[int]:
    """Returns a set of item type IDs that have a market group ID."""
    market_types = {
        type_id
        for type_id, type_info in eve_types.items()
        if type_info.marketGroupID is not None
    }
    return frozenset(market_types)


def manufactured_items_blueprint_lookup(
    blueprints: dict[int, YR.Blueprints],
) -> dict[int, int]:
    """Returns a mapping of item type IDs to blueprint type IDs that can produce them."""
    produced: dict[int, int] = {}
    for blueprint in blueprints.values():
        if blueprint.activities.manufacturing is not None:
            if blueprint.activities.manufacturing.products is not None:
                for product in blueprint.activities.manufacturing.products:
                    produced[product.typeID] = blueprint.blueprintTypeID
    return produced


def reaction_items_blueprint_lookup(
    blueprints: dict[int, YR.Blueprints],
) -> dict[int, int]:
    """Returns a mapping of item type IDs to blueprint type IDs that can produce them."""
    produced: dict[int, int] = {}
    for blueprint in blueprints.values():
        if blueprint.activities.reaction is not None:
            if blueprint.activities.reaction.products is not None:
                for product in blueprint.activities.reaction.products:
                    produced[product.typeID] = blueprint.blueprintTypeID
    return produced


def blueprints_in_market(
    blueprints: dict[int, YR.Blueprints],
    types_in_market: set[int],
) -> frozenset[int]:
    """Returns a set of blueprint type IDs that are published and have a market group ID."""
    in_market = {
        blueprint.blueprintTypeID
        for blueprint in blueprints.values()
        if blueprint.blueprintTypeID in types_in_market
    }
    return frozenset(in_market)


def market_path_int(
    market_group_id: int, market_groups: dict[int, YR.MarketGroups]
) -> tuple[int, ...]:
    """Get the path of market group IDs from the root to the specified market group."""
    path: list[int] = []
    current_id = market_group_id
    while current_id is not None:
        path.append(current_id)
        current_group = market_groups.get(current_id)
        if current_group is None:
            raise ValueError(
                f"Market group ID {current_id} not found in market groups."
            )
        current_id = current_group.parentGroupID
    return tuple(reversed(path))


def market_path_str(
    market_group_id: int, market_groups: dict[int, YR.MarketGroups], lang: Lang = "en"
) -> tuple[str, ...]:
    """Get the path of market group names from the root to the specified market group."""
    path: list[str] = []
    current_id = market_group_id
    while current_id is not None:
        current_group = market_groups.get(current_id)
        if current_group is None:
            raise ValueError(
                f"Market group ID {current_id} not found in market groups."
            )
        path.append(current_group.localized_name(lang))
        current_id = current_group.parentGroupID
    return tuple(reversed(path))


@dataclass
class MarketPath:
    market_group_id: int
    market_path_str: tuple[str, ...]
    market_path_int: tuple[int, ...]

    def delimited_str_path(self, delimiter: str = " - ") -> str:
        """Returns the market path as a delimited string."""
        return delimiter.join(self.market_path_str)

    def delimited_int_path(self, delimiter: str = " - ") -> str:
        """Returns the market path as a delimited string of integers."""
        return delimiter.join(str(id) for id in self.market_path_int)


type CollectedMarketPaths = dict[int, MarketPath]


def collect_market_paths(
    market_groups: dict[int, YR.MarketGroups], lang: Lang = "en"
) -> CollectedMarketPaths:
    """Collects market paths for all market groups."""
    collected: CollectedMarketPaths = {}
    for market_group_id in market_groups.keys():
        try:
            path_str = market_path_str(market_group_id, market_groups, lang)
            path_int = market_path_int(market_group_id, market_groups)
            collected[market_group_id] = MarketPath(
                market_group_id=market_group_id,
                market_path_str=path_str,
                market_path_int=path_int,
            )
        except ValueError as e:
            logger.warning(f"Skipping market group ID {market_group_id}: {e}")
    return collected
