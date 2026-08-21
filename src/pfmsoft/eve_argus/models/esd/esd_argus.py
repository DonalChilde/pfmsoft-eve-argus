"""Static data models customized for Argus usage."""

import logging
from dataclasses import dataclass, field

from pfmsoft.eve_argus.models.esd.esd_datasets import BlueprintsDataset, TypesDataset

logger = logging.getLogger(__name__)


@dataclass(slots=True, kw_only=True)
class ArgusBlueprintsDataset(BlueprintsDataset):
    """Blueprints dataset customized for Argus usage."""

    manufactured_to_blueprint_id: dict[int, int] = field(
        default_factory=dict[int, int], init=False
    )
    """Mapping of manufactured type IDs to blueprint type IDs."""
    manufactured_portion_size: dict[int, int] = field(
        default_factory=dict[int, int], init=False
    )
    """Mapping of manufactured type IDs to portion sizes."""
    manufacturing_blueprints: set[int] = field(default_factory=set[int], init=False)
    """Set of blueprint type IDs that have manufacturing activities."""
    reaction_to_blueprint_id: dict[int, int] = field(
        default_factory=dict[int, int], init=False
    )
    """Mapping of reaction type IDs to blueprint type IDs."""
    reaction_blueprints: set[int] = field(default_factory=set[int], init=False)
    """Set of blueprint type IDs that have reaction activities."""
    reaction_portion_size: dict[int, int] = field(
        default_factory=dict[int, int], init=False
    )
    """Mapping of reaction type IDs to portion sizes."""
    published_blueprints: set[int] = field(default_factory=set[int], init=False)
    """Set of blueprint type IDs that are published."""

    @classmethod
    def from_datasets(
        cls, blueprints: BlueprintsDataset, types: TypesDataset
    ) -> ArgusBlueprintsDataset:
        """Create an ArgusBlueprintsDataset from BlueprintsDataset and TypesDataset."""
        argus_blueprints = cls(dataset=blueprints.dataset)
        argus_blueprints._fill_manufactured_to_blueprint_id()
        argus_blueprints._fill_reaction_to_blueprint_id()
        argus_blueprints._fill_manufactured_portion_size(types)
        argus_blueprints._fill_reaction_portion_size(types)
        argus_blueprints._fill_published_blueprints(types)
        return argus_blueprints

    def __post_init__(self) -> None:
        """Post-initialization to check proper initialization."""
        if not self.manufacturing_blueprints:
            logger.warning(
                "ArgusBlueprintsDataset is not fully initialized. "
                "Use from_datasets() to create a fully initialized instance."
            )
            raise ValueError(
                "ArgusBlueprintsDataset is not fully initialized. "
                "Use from_datasets() to create a fully initialized instance."
            )

    def _fill_manufactured_to_blueprint_id(self) -> None:
        """Fill the mapping of manufactured type IDs to blueprint type IDs."""
        for blueprint in self.dataset.values():
            if blueprint.activities.manufacturing is not None:
                if blueprint.activities.manufacturing.products is not None:
                    if len(blueprint.activities.manufacturing.products) > 0:
                        logger.warning(
                            "Blueprint %d has multiple manufacturing products, "
                            "only the first one will be used.",
                            blueprint.blueprintTypeID,
                        )
                    self.manufactured_to_blueprint_id[
                        blueprint.activities.manufacturing.products[0].typeID
                    ] = blueprint.blueprintTypeID
        self.manufacturing_blueprints = set(self.manufactured_to_blueprint_id.values())

    def _fill_reaction_to_blueprint_id(self) -> None:
        """Fill the mapping of reaction type IDs to blueprint type IDs."""
        for blueprint in self.dataset.values():
            if blueprint.activities.reaction is not None:
                if blueprint.activities.reaction.products is not None:
                    if len(blueprint.activities.reaction.products) > 0:
                        logger.warning(
                            "Blueprint %d has multiple reaction products, "
                            "only the first one will be used.",
                            blueprint.blueprintTypeID,
                        )
                    self.reaction_to_blueprint_id[
                        blueprint.activities.reaction.products[0].typeID
                    ] = blueprint.blueprintTypeID
        self.reaction_blueprints = set(self.reaction_to_blueprint_id.values())

    def _fill_manufactured_portion_size(self, types: TypesDataset) -> None:
        """Fill the mapping of manufactured type IDs to portion sizes."""
        for manufactured_type_id in self.manufactured_to_blueprint_id.keys():
            manufactured_type = types.dataset.get(manufactured_type_id)
            if manufactured_type is not None:
                self.manufactured_portion_size[manufactured_type_id] = (
                    manufactured_type.portionSize
                )

    def _fill_reaction_portion_size(self, types: TypesDataset) -> None:
        """Fill the mapping of reaction type IDs to portion sizes."""
        for reaction_type_id in self.reaction_to_blueprint_id.keys():
            reaction_type = types.dataset.get(reaction_type_id)
            if reaction_type is not None:
                self.reaction_portion_size[reaction_type_id] = reaction_type.portionSize

    def _fill_published_blueprints(self, types: TypesDataset) -> None:
        """Fill the set of published blueprint type IDs."""
        for blueprint_type_id in self.dataset.keys():
            blueprint_type = types.dataset.get(blueprint_type_id)
            if blueprint_type is not None and blueprint_type.published:
                self.published_blueprints.add(blueprint_type_id)
