"""Shared market-history type discovery and static selection."""

from pfmsoft.eve_link import EsiLink, EsiSchema, FailedEsiResponse

from pfmsoft.eve_argus.esi import fetch as EsiFetch
from pfmsoft.eve_argus.esi import validate as EsiValidate
from pfmsoft.eve_argus.helpers.market_groups import filter_type_ids_by_market_path
from pfmsoft.eve_argus.static.models import MarketGroupsDataset, TypesDataset


async def active_type_ids(
    esi_link: EsiLink, schema: EsiSchema, *, region_id: int
) -> set[int]:
    """Discover regional active types through ESI's paginated request flow.

    Raises:
        ValueError: If ESI returns a failed response or invalid type data.
    """
    response = await EsiFetch.market_types(esi_link, schema, region_id=region_id)
    if isinstance(response, FailedEsiResponse):
        reasons = [
            message.strip()
            for message in response.failed_response.error_messages
            if message.strip()
        ]
        raise ValueError(
            "; ".join(reasons)
            or "ESI request failed without an error reason from pfmsoft.api_request."
        )
    return set(EsiValidate.market_types(response).type_ids)


def select_market_type_ids(
    *,
    market_groups: MarketGroupsDataset,
    types: TypesDataset,
    include: set[int],
    exclude: set[int],
) -> set[int]:
    """Validate static paths and select published, market-listed types.

    Raises:
        ValueError: If datasets are missing, filters are unknown, or published
            type/group references are inconsistent.
    """
    if not market_groups or not types:
        raise ValueError("Static market groups and published types must be populated.")
    unknown = (include | exclude) - market_groups.keys()
    if unknown:
        raise ValueError(f"Unknown market group IDs: {sorted(unknown)}")

    published_ids = {key for key, record in types.items() if record.published}
    for type_id in published_ids:
        record = types[type_id]
        if record.type_id != type_id:
            raise ValueError(f"Static type key {type_id} disagrees with record ID.")
        if (
            record.market_group_id is not None
            and record.market_group_id not in market_groups
        ):
            raise ValueError(
                f"Missing market group {record.market_group_id} for type {type_id}."
            )
    for group_id, group in market_groups.items():
        if (
            group.market_group_id != group_id
            or not group.int_path
            or group.int_path[-1] != group_id
            or not set(group.int_path) <= market_groups.keys()
        ):
            raise ValueError(f"Invalid market path for group {group_id}.")
        for type_id in group.types:
            if type_id in published_ids and types[type_id].market_group_id != group_id:
                raise ValueError(
                    f"Market group {group_id} has an inconsistent reference to type {type_id}."
                )
    return (
        filter_type_ids_by_market_path(
            market_groups, include=include or None, exclude=exclude
        )
        & published_ids
    )
