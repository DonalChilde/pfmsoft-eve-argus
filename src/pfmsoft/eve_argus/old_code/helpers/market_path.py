"""Functions to get the path of market groups from the root to a specified market group, either as a tuple of IDs or a tuple of names."""

from eve_static_data.models.yaml_records import MarketGroups


def market_path_int(
    market_group_id: int, market_groups: dict[int, MarketGroups]
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
    market_group_id: int, market_groups: dict[int, MarketGroups]
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
        path.append(current_group.name)
        current_id = current_group.parentGroupID
    return tuple(reversed(path))
