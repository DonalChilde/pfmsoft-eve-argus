"""Transforms ESI market group details to Argus market group models."""

from pfmsoft.eve_argus.models.esi import esi_argus, esi_response


def _build_market_group_paths(
    esi_market_groups: dict[int, esi_response.GetMarketsGroupsMarketGroupId],
) -> tuple[dict[int, tuple[str, ...]], dict[int, tuple[int, ...]]]:
    """Build the ancestor-name and ancestor-ID path chains for each market group."""
    path_str: dict[int, tuple[str, ...]] = {}
    path_int: dict[int, tuple[int, ...]] = {}

    def build_path_str(market_group_id: int) -> tuple[str, ...]:
        if market_group_id in path_str:
            return path_str[market_group_id]

        market_group = esi_market_groups[market_group_id].market_group
        if market_group.parent_group_id is None:
            result = (market_group.name,)
        elif market_group.parent_group_id in esi_market_groups:
            result = build_path_str(market_group.parent_group_id) + (market_group.name,)
        else:
            result = (market_group.name,)

        path_str[market_group_id] = result
        return result

    def build_path_int(market_group_id: int) -> tuple[int, ...]:
        if market_group_id in path_int:
            return path_int[market_group_id]

        market_group = esi_market_groups[market_group_id].market_group
        if market_group.parent_group_id is None:
            result = (market_group.market_group_id,)
        elif market_group.parent_group_id in esi_market_groups:
            result = build_path_int(market_group.parent_group_id) + (
                market_group.market_group_id,
            )
        else:
            result = (market_group.market_group_id,)

        path_int[market_group_id] = result
        return result

    for market_group_id in esi_market_groups:
        build_path_str(market_group_id)
        build_path_int(market_group_id)

    return path_str, path_int


def transform_market_groups(
    esi_market_groups: dict[int, esi_response.GetMarketsGroupsMarketGroupId],
) -> dict[int, esi_argus.MarketGroup]:
    """Transforms ESI market group details to Argus market group models.

    Args:
        esi_market_groups: A dictionary of ESI market group details keyed by market group ID.

    Returns:
        A dictionary of Argus MarketGroup models keyed by market group ID.
    """
    path_str, path_int = _build_market_group_paths(esi_market_groups)
    argus_market_groups: dict[int, esi_argus.MarketGroup] = {}
    for market_group_id, esi_group in esi_market_groups.items():
        detail = esi_group.market_group
        argus_group = esi_argus.MarketGroup(
            received_at=esi_group.received_at,
            expires_at=esi_group.expires_at,
            market_group_id=detail.market_group_id,
            name=detail.name,
            description=detail.description,
            parent_group_id=detail.parent_group_id,
            types=detail.types,
            path_str=path_str.get(market_group_id, ()),
            path_int=path_int.get(market_group_id, ()),
        )
        argus_market_groups[market_group_id] = argus_group
    return argus_market_groups
