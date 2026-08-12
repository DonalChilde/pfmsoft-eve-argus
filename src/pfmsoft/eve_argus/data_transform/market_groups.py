from pfmsoft.eve_argus.models.esi.esi_argus import MarketGroup
from pfmsoft.eve_argus.models.esi.esi_response import GetMarketsGroupsMarketGroupId


def transform_market_groups(
    esi_market_groups: dict[int, GetMarketsGroupsMarketGroupId],
) -> dict[int, MarketGroup]:
    """Transforms ESI market group details to Argus market group models.

    Args:
        esi_market_groups: A dictionary of ESI market group details keyed by market group ID.

    Returns:
        A dictionary of Argus MarketGroup models keyed by market group ID.
    """
    argus_market_groups: dict[int, MarketGroup] = {}
    for market_group_id, esi_group in esi_market_groups.items():
        argus_group = MarketGroup(
            received_at=esi_group.received_at,
            expires_at=esi_group.expires_at,
            market_group_id=esi_group.market_group_id,
            name=esi_group.name,
            description=esi_group.description,
            parent_group_id=esi_group.parent_group_id,
            types=esi_group.types,
            path_str=(),  # Placeholder for path_str
            path_int=(),  # Placeholder for path_int
        )
        argus_market_groups[market_group_id] = argus_group
    return argus_market_groups
