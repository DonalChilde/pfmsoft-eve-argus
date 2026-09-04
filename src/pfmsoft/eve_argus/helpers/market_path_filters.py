"""Helpers for filtering market-group type IDs by ancestor paths."""

from pfmsoft.eve_argus.models.esi.argus_response_models import MarketGroup


def filter_type_ids_by_market_path(
    market_groups: dict[int, MarketGroup],
    include: set[int] | None = None,
    exclude: set[int] | None = None,
) -> set[int]:
    """Filters type IDs by market path from the given market groups.

    Market groups that represent the terminus of a market path (i.e., those without
    child groups) can have type IDs associated with them. This function collects those
    type IDs based on the specified include and exclude market path filters.

    The function iterates over the provided market groups and collects type IDs that match
    the specified market path filters. If both include and exclude filters are provided,
    the include filter is applied first, followed by the exclude filter.

    Args:
        market_groups: A dictionary of market group IDs to MarketGroup objects.
        include: An optional set of market paths to include. None means include all.
        exclude: An optional set of market paths to exclude. None means exclude none.

    Returns:
        A set of type IDs that match the market path filters.

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
            if include.isdisjoint(market_group.path_int):
                continue
            result.update(market_group.types)

    if exclude is not None:
        for market_group in market_groups.values():
            if exclude.isdisjoint(market_group.path_int):
                continue
            result.difference_update(market_group.types)

    return result
