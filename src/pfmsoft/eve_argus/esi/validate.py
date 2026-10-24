"""Validation functions for ESI responses."""

from itertools import chain
from typing import Any

from pfmsoft.eve_link import (
    EsiResponse,
)

from pfmsoft.eve_argus.esi import models

# from pfmsoft.eve_argus.models.esi import esi_response_models as ERM


def _expires_at_from_response(response: EsiResponse) -> str | None:
    """Extracts the expires_at timestamp from an ESI response."""
    expires_at = response.response.metadata.expires_at_instant
    if expires_at:
        return expires_at.format_iso()
    return None


def _received_at_from_response(response: EsiResponse) -> str:
    """Extracts the received_at timestamp from an ESI response."""
    return response.response.metadata.received_at


def market_history(response: EsiResponse) -> models.GetMarketsRegionIdHistory:
    """Validates market history response from ESI."""
    response_dict: dict[str, Any] = {
        "received_at": _received_at_from_response(response),
        "expires_at": _expires_at_from_response(response),
        "region_id": response.esi_request.path_parameters["region_id"],
        "type_id": response.esi_request.query_parameters["type_id"],
        "history": response.response_data,
    }
    history = models.GetMarketsRegionIdHistory.model_validate(response_dict)
    return history


def system_cost_indices(response: EsiResponse) -> models.GetIndustrySystems:
    """Validates system cost indices response."""
    response_dict: dict[str, Any] = {
        "received_at": _received_at_from_response(response),
        "expires_at": _expires_at_from_response(response),
        "industry_systems": response.response_data,
    }
    return models.GetIndustrySystems.model_validate(response_dict)


def region_market_orders(
    response: EsiResponse,
) -> models.GetMarketsRegionIdOrders:
    """Validates region market orders."""
    response_dict: dict[str, Any] = {
        "received_at": _received_at_from_response(response),
        "expires_at": _expires_at_from_response(response),
        "region_id": response.esi_request.path_parameters["region_id"],
        "orders": response.response_data,
    }
    return models.GetMarketsRegionIdOrders.model_validate(response_dict)


def markets_prices(response: EsiResponse) -> models.GetMarketsPrices:
    """Validates market prices."""
    response_dict: dict[str, Any] = {
        "received_at": _received_at_from_response(response),
        "expires_at": _expires_at_from_response(response),
        "markets_prices": response.response_data,
    }
    return models.GetMarketsPrices.model_validate(response_dict)


def universe_names(responses: list[EsiResponse]) -> models.PostUniverseNames:
    """Validates universe names."""
    combined_response_data = list(
        chain.from_iterable([r.response_data for r in responses])
    )
    response_dict: dict[str, Any] = {
        "received_at": _received_at_from_response(responses[0]),
        "expires_at": _expires_at_from_response(responses[0]),
        "names": combined_response_data,
    }
    return models.PostUniverseNames.model_validate(response_dict)


def corporation_industry_jobs(
    response: EsiResponse,
) -> models.GetCorporationsCorporationIdIndustryJobs:
    """Validates corporation industry jobs."""
    response_dict: dict[str, Any] = {
        "received_at": _received_at_from_response(response),
        "expires_at": _expires_at_from_response(response),
        "corporation_id": response.esi_request.path_parameters["corporation_id"],
        "industry_jobs": response.response_data,
    }
    return models.GetCorporationsCorporationIdIndustryJobs.model_validate(response_dict)


def corporation_blueprints(
    response: EsiResponse,
) -> models.GetCorporationsCorporationIdBlueprints:
    """Validates corporation blueprints."""
    response_dict: dict[str, Any] = {
        "received_at": _received_at_from_response(response),
        "expires_at": _expires_at_from_response(response),
        "corporation_id": response.esi_request.path_parameters["corporation_id"],
        "blueprints": response.response_data,
    }
    return models.GetCorporationsCorporationIdBlueprints.model_validate(response_dict)


def universe_type_ids(
    response: EsiResponse,
) -> models.GetUniverseTypes:
    """Validates universe type IDs."""
    response_dict: dict[str, Any] = {
        "received_at": _received_at_from_response(response),
        "expires_at": _expires_at_from_response(response),
        "type_ids": response.response_data,
    }
    return models.GetUniverseTypes.model_validate(response_dict)


def market_types(response: EsiResponse) -> models.GetMarketsRegionIdTypes:
    """Validates market types for a region."""
    response_dict: dict[str, Any] = {
        "received_at": _received_at_from_response(response),
        "expires_at": _expires_at_from_response(response),
        "region_id": response.esi_request.path_parameters["region_id"],
        "type_ids": response.response_data,
    }
    return models.GetMarketsRegionIdTypes.model_validate(response_dict)
