"""Tests for the example_project namespace package."""

from pfmsoft.eve_argus.data_transform.market_groups import transform_market_groups
from pfmsoft.eve_argus.models.esi.esi_response_models import (
    GetMarketsGroupsMarketGroupId,
    GetMarketsGroupsMarketGroupIdDetail,
)


def test_transform_market_groups_builds_parent_paths():
    """Nested market group IDs should carry their ancestor chain as path values."""
    root_group = GetMarketsGroupsMarketGroupId(
        received_at="2024-01-01T00:00:00Z",
        expires_at=None,
        market_group=GetMarketsGroupsMarketGroupIdDetail(
            market_group_id=10,
            name="Root",
            description="root group",
            parent_group_id=None,
            types=[100],
        ),
    )
    child_group = GetMarketsGroupsMarketGroupId(
        received_at="2024-01-01T00:00:00Z",
        expires_at=None,
        market_group=GetMarketsGroupsMarketGroupIdDetail(
            market_group_id=20,
            name="Child",
            description="child group",
            parent_group_id=10,
            types=[200],
        ),
    )

    transformed = transform_market_groups({10: root_group, 20: child_group})

    assert transformed[10].path_str == ("Root",)
    assert transformed[10].path_int == (10,)
    assert transformed[20].path_str == ("Root", "Child")
    assert transformed[20].path_int == (10, 20)
