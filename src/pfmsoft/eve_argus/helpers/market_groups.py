"""Helpers for filtering market-group type IDs by ancestor paths."""

from pfmsoft.eve_argus.models.argus.static import (
    MarketGroupsDataset,
    MarketGroupsRecord,
)


def filter_type_ids_by_market_path(
    market_groups: MarketGroupsDataset,
    include: set[int] | None = None,
    exclude: set[int] | None = None,
) -> set[int]:
    """Filters type IDs by market path from the given market groups based on market_group_id filters.

    Market groups that represent the terminus of a market path (i.e., those without
    child groups) can have type IDs associated with them. This function collects those
    type IDs based on the specified include and exclude market_group_id filters.

    The function iterates over the provided market groups and collects type IDs that match
    the specified market_group_id filters. If both include and exclude filters are provided,
    the include filter is applied first, followed by the exclude filter.

    Args:
        market_groups: A dictionary of market group IDs to MarketGroupsRecord objects.
        include: An optional set of market_group_ids to include. None means include all.
        exclude: An optional set of market_group_ids to exclude. None means exclude none.

    Returns:
        A set of type IDs that match the market_group_id filters.

    Raises:
        ValueError: If include is an empty set.
    """
    if include is not None and not include:
        raise ValueError("include must not be empty")

    result: set[int] = set()
    if include is None:
        for market_group in market_groups.values():
            result.update(market_group.types)
    else:
        for market_group in market_groups.values():
            if include.isdisjoint(market_group.int_path):
                continue
            result.update(market_group.types)

    if exclude is not None:
        for market_group in market_groups.values():
            if exclude.isdisjoint(market_group.int_path):
                continue
            result.difference_update(market_group.types)
    return result


def int_path_string(market_group: MarketGroupsRecord, sep: str = "/") -> str:
    """Converts the integer path of a market group to a string representation.

    Args:
        market_group: The market group whose integer path is to be converted.
        sep: The separator to use between path elements. Defaults to "/".

    Returns:
        A string representation of the market group's integer path.
    """
    return sep.join(str(i) for i in market_group.int_path)


def str_path_string(market_group: MarketGroupsRecord, sep: str = "/") -> str:
    """Converts the string path of a market group to a string representation.

    Args:
        market_group: The market group whose string path is to be converted.
        sep: The separator to use between path elements. Defaults to "/".

    Returns:
        A string representation of the market group's string path.
    """
    return sep.join(market_group.str_path)
