from pathlib import Path

from pfmsoft.eve_argus.data_transform import (
    history_summary,
    market_groups,
    order_summaries,
    regional_market_orders,
)
from pfmsoft.eve_argus.models.esi import esi_argus, esi_response

PROOF_OUTPUT_DIR = Path(__file__).parent / "proof-output"
PROOF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MARKET_GROUP_IDS_FILENAME = PROOF_OUTPUT_DIR / "market_group_ids_response.json"
MARKET_GROUPS_DETAILS_FILENAME = (
    PROOF_OUTPUT_DIR / "market_groups_details_collected_response.json"
)
REGION_MARKET_ORDERS_FILENAME = PROOF_OUTPUT_DIR / "region_market_orders_response.json"
REGION_MARKET_HISTORY_FILENAME = (
    PROOF_OUTPUT_DIR / "region_market_history_collected_response.json"
)
MARKETS_PRICES_FILENAME = PROOF_OUTPUT_DIR / "markets_prices_response.json"
INDUSTRY_SYSTEMS_FILENAME = PROOF_OUTPUT_DIR / "industry_systems_response.json"

# Transformed data output filenames
REGION_HISTORY_SUMMARY_FILENAME = PROOF_OUTPUT_DIR / "region_history_summary.json"
MARKET_GROUPS_TRANSFORMED_FILENAME = PROOF_OUTPUT_DIR / "market_groups_transformed.json"
REGION_MARKET_ORDERS_TRANSFORMED_FILENAME = (
    PROOF_OUTPUT_DIR / "region_market_orders_transformed.json"
)
ORDER_SUMMARIES_TRANSFORMED_FILENAME = (
    PROOF_OUTPUT_DIR / "order_summaries_transformed.json"
)


def history_summary_transform():
    """Proof the history summary calculation."""
    # NOTE that this assumes that all the histories are from the same region, which is
    # only guaranteed true for this test data set.
    print()
    print(f"Loading history response from {REGION_MARKET_HISTORY_FILENAME}")
    history_response = (
        esi_response.GetMarketsRegionIdHistoryCollectedResponse.deserialize(
            REGION_MARKET_HISTORY_FILENAME.read_text()
        )
    )
    regional_histories: history_summary.RegionalHistories = {}
    for entry in history_response.response_data:
        region_id, type_id = entry.region_id, entry.type_id
        regional_histories.setdefault(region_id, {})[type_id] = entry

    result = history_summary.calculate_regional_history_summaries(
        regional_histories=regional_histories, period=7
    )
    return result


def market_groups_transform():
    """Proof the market groups transformation."""
    print()
    print(f"Loading market group details from {MARKET_GROUPS_DETAILS_FILENAME}")
    market_groups_details_response = (
        esi_response.GetMarketsGroupsMarketGroupIdCollectedResponse.deserialize(
            MARKET_GROUPS_DETAILS_FILENAME.read_text()
        )
    )
    result = market_groups.transform_market_groups(
        esi_market_groups=market_groups_details_response.response_data
    )
    return result


def regional_market_orders_transform():
    """Proof the regional market orders transformation."""
    print()
    print(f"Loading regional market orders from {REGION_MARKET_ORDERS_FILENAME}")
    regional_market_orders_response = (
        esi_response.GetMarketsRegionIdOrdersResponse.deserialize(
            REGION_MARKET_ORDERS_FILENAME.read_text()
        )
    )
    result = regional_market_orders.transform_region_market_orders(
        region_market_orders=regional_market_orders_response.response_data
    )
    return result


def order_summaries_transform():
    """Proof the order summaries transformation."""
    print()
    print(
        f"Loading regional market orders from {REGION_MARKET_ORDERS_TRANSFORMED_FILENAME}"
    )
    region_market_orders = esi_argus.RegionMarketOrders.deserialize(
        REGION_MARKET_ORDERS_TRANSFORMED_FILENAME.read_text()
    )
    result = order_summaries.calculate_summaries(region_orders=region_market_orders)
    return result


if __name__ == "__main__":
    history_summary_result = history_summary_transform()
    REGION_HISTORY_SUMMARY_FILENAME.write_text(
        history_summary_result.serialize(indent=2)
    )
    print(f"History summary written to {REGION_HISTORY_SUMMARY_FILENAME}")

    market_groups_result = market_groups_transform()
    market_groups_dataset = esi_argus.MarketGroupsDataset(dataset=market_groups_result)
    MARKET_GROUPS_TRANSFORMED_FILENAME.write_text(
        market_groups_dataset.serialize(indent=2)
    )
    print(f"Market groups transformed written to {MARKET_GROUPS_TRANSFORMED_FILENAME}")

    regional_market_orders_result = regional_market_orders_transform()
    REGION_MARKET_ORDERS_TRANSFORMED_FILENAME.write_text(
        regional_market_orders_result.serialize(indent=2)
    )
    print(
        f"Regional market orders transformed written to {REGION_MARKET_ORDERS_TRANSFORMED_FILENAME}"
    )

    order_summaries_result = order_summaries_transform()

    ORDER_SUMMARIES_TRANSFORMED_FILENAME.write_text(
        order_summaries_result.serialize(indent=2)
    )
    print(
        f"Order summaries transformed written to {ORDER_SUMMARIES_TRANSFORMED_FILENAME}"
    )
