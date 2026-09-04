"""Tests for market path filtering helpers."""

import pytest

from pfmsoft.eve_argus.helpers.market_path_filters import (
    filter_type_ids_by_market_path,
)
from pfmsoft.eve_argus.models.esi.argus_response_models import MarketGroup


def test_filter_type_ids_by_market_path_rejects_empty_include() -> None:
    """An empty include filter should be rejected explicitly."""
    with pytest.raises(ValueError, match="include must not be empty"):
        filter_type_ids_by_market_path({}, include=set())


def test_filter_type_ids_by_market_path_removes_previously_added_excluded_types() -> (
    None
):
    """Excluded types should be removed even when added by an earlier group."""
    market_groups = {
        1: MarketGroup(
            received_at="2024-01-01T00:00:00Z",
            expires_at=None,
            market_group_id=1,
            name="Included",
            description="included group",
            types=[100, 200],
            path_int=(1,),
        ),
        2: MarketGroup(
            received_at="2024-01-01T00:00:00Z",
            expires_at=None,
            market_group_id=2,
            name="Excluded",
            description="excluded group",
            types=[200, 300],
            path_int=(1, 2),
        ),
    }

    result = filter_type_ids_by_market_path(
        market_groups,
        include={1},
        exclude={2},
    )

    assert result == {100}
