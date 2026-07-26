import logging

from eve_static_data.models import yaml_records as YR

from esi_link.argus.models.esi_models import GetMarketsPrices

logger = logging.getLogger(__name__)


def calculate_manufacturing_eivs(
    blueprints: dict[int, YR.Blueprints],
    universe_pricing: GetMarketsPrices,
) -> dict[int, float]:
    """Calculate the EIV for all manufacturing blueprints."""
    eivs: dict[int, float] = {}
    prices: dict[int, float] = {
        type_id: price.adjusted_price
        for type_id, price in universe_pricing.prices.items()
        if price.adjusted_price is not None
    }
    for blueprint in blueprints.values():
        if blueprint.activities.manufacturing is not None:
            if blueprint.activities.manufacturing.materials is not None:
                try:
                    eiv = calculate_eiv(
                        blueprint.activities.manufacturing.materials,
                        prices,
                    )
                    eivs[blueprint.blueprintTypeID] = eiv
                except ValueError as e:
                    logger.warning(
                        f"Could not calculate EIV for blueprint {blueprint.blueprintTypeID}: {e}"
                    )
    return eivs


def calculate_eiv(materials: list[YR.Materials], prices: dict[int, float]) -> float:
    """Calculate the EIV for a given list of materials and their prices."""
    total_eiv = 0.0
    for material in materials:
        price = prices.get(material.typeID)
        if price is None:
            raise ValueError(f"Price not found for type ID {material.typeID}")
        total_eiv += material.quantity * price
    return total_eiv
