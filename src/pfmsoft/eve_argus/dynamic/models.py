"""Models related to the dynamic database.

The model shapes primarily represent data retrieved from the database.
Where appropriate, the field data is transformed into the correct Python types.
For example, currency values are stored as Integers in the database but are transformed into Decimal in Python.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(slots=True, kw_only=True, frozen=True)
class ResponseMetadata:
    response_metadata_id: int
    received_at: str
    expires_at: str | None
    argus_expires_at: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class EsiDataset(ResponseMetadata):
    """Represents a dataset retrieved from the Argus dynamic database."""

    records: Any
    """The actual records contained in the dataset, should be overridden by subclasses."""


@dataclass(slots=True, kw_only=True, frozen=True)
class SystemCostIndexRecord:
    system_id: int
    copying: Decimal | None
    manufacturing: Decimal | None
    invention: Decimal | None
    reaction: Decimal | None
    researching_material_efficiency: Decimal | None
    researching_time_efficiency: Decimal | None
    response_metadata_id: int


@dataclass(slots=True, kw_only=True, frozen=True)
class SystemCostIndicesDataset(EsiDataset):
    records: dict[int, SystemCostIndexRecord]


@dataclass(slots=True, kw_only=True, frozen=True)
class SystemCostIndicesResponse(ResponseMetadata):
    """Represents a system cost index response.

    Note that this model does not contain extra fields for Universe prices
    because none are defined in the table. This model is included for completness,
    to match the pattern of response models that DO have extra fields.
    """


@dataclass(slots=True, kw_only=True, frozen=True)
class MarketsPriceRecord:
    type_id: int
    average_price: Decimal | None
    adjusted_price: Decimal | None
    response_metadata_id: int


@dataclass(slots=True, kw_only=True, frozen=True)
class MarketsPricesDataset(EsiDataset):
    records: dict[int, MarketsPriceRecord]


@dataclass(slots=True, kw_only=True, frozen=True)
class MarketsPricesResponse(ResponseMetadata):
    """Represents a universe markets prices response.

    Note that this model does not contain extra fields for Universe prices
    because none are defined in the table. This model is included for completness,
    to match the pattern of response models that DO have extra fields.
    """


@dataclass(slots=True, kw_only=True, frozen=True)
class CorporationIndustryJobRow:
    """A stored industry job, including IDs from several unrelated namespaces.

    Do not send all ID fields to PostUniverseNames. blueprint_id identifies an item,
    job_id identifies a job, and response_metadata_id is local database metadata.
    activity_id belongs to the static industry activities dataset; small activity or
    response IDs may resolve to unrelated inventory types without an API error.
    blueprint_type_id and product_type_id have names in the static types dataset.

    blueprint_location_id and output_location_id may identify private corporation
    locations. In the development snapshot probed on 2026-10-18, these were 64-bit
    IDs rejected with HTTP 400 because PostUniverseNames requires int32 IDs. Exclude
    these fields from report name lookups and retain their raw IDs with UNKNOWN names.
    facility_id and location_id resolved as public stations in that sample, but may
    instead identify private structures, which also cannot be sent as int32 IDs.
    This sample does not establish that every in-range location is publicly resolvable.
    """

    corporation_id: int
    activity_id: int
    """The activity ID associated with the industry job. From industry_activities table."""
    blueprint_id: int
    blueprint_location_id: int
    """The location ID of the blueprint. Not a valid target for universe_names."""
    blueprint_type_id: int
    completed_character_id: int | None
    completed_date: str | None
    cost: Decimal | None
    duration: int
    end_date: str
    facility_id: int
    installer_id: int
    job_id: int
    licensed_runs: int | None
    location_id: int
    output_location_id: int
    """The output location ID. Not a valid target for universe_names."""
    pause_date: str | None
    probability: float | None
    product_type_id: int | None
    runs: int
    start_date: str
    status: str
    successful_runs: int | None
    response_metadata_id: int
    """The response metadata ID associated with the industry job."""


@dataclass(slots=True, kw_only=True, frozen=True)
class CorporationIndustryJobsDataset(EsiDataset):
    corporation_id: int
    records: dict[int, CorporationIndustryJobRow]


@dataclass(slots=True, kw_only=True, frozen=True)
class CorporationIndustryJobsResponse(ResponseMetadata):
    """Represents a corporation industry jobs response."""

    corporation_id: int


@dataclass(slots=True, kw_only=True, frozen=True)
class CorporationBlueprintRecord:
    """A stored original, original stack, or copy, preserving raw ESI sentinels.

    quantity -1 means one original, -2 means one copy, and positive values count
    stacked originals. runs is not an item count and remains unmodified.
    item_id and response_metadata_id are not universe-name lookup identifiers.
    location_id may identify a station, private structure, or container; only
    eligible station IDs are submitted to public name lookup by blueprint reports.
    """

    """Represents a corporation blueprint record.

    Note that `quantity` is -1 for a blueprint original, -2 for a blueprint copy,
    and a positive integer for an unprocessed stack of originals (e.g. fresh from the
    market). `runs` is -1 for an original, otherwise the number of runs remaining
    on the copy.
    """

    corporation_id: int
    item_id: int
    type_id: int
    location_id: int
    location_flag: str
    quantity: int
    time_efficiency: int
    material_efficiency: int
    runs: int
    response_metadata_id: int


@dataclass(slots=True, kw_only=True, frozen=True)
class CorporationBlueprintsDataset(EsiDataset):
    corporation_id: int
    records: dict[int, CorporationBlueprintRecord]


@dataclass(slots=True, kw_only=True, frozen=True)
class CorporationBlueprintsResponse(ResponseMetadata):
    """Represents a corporation blueprints response."""

    corporation_id: int


@dataclass(slots=True, kw_only=True, frozen=True)
class MarketOrderRecord:
    """Represents a market order record retrieved from the database."""

    response_metadata_id: int
    region_id: int
    duration: int
    is_buy_order: bool
    issued: str
    location_id: int
    min_volume: int
    order_id: int
    price: Decimal
    range: str
    system_id: int
    type_id: int
    volume_remain: int
    volume_total: int


@dataclass(slots=True, kw_only=True, frozen=True)
class BuySellOrders:
    """Represents a collection of buy and sell market orders for one region and type_id."""

    buy_orders: tuple[MarketOrderRecord, ...]
    sell_orders: tuple[MarketOrderRecord, ...]

    def __post_init__(self) -> None:
        """Post-initialization hook for BuySellOrders."""
        # Ensure that the orders are sorted by price.
        object.__setattr__(
            self,
            "buy_orders",
            tuple(sorted(self.buy_orders, key=lambda o: o.price, reverse=True)),
        )
        object.__setattr__(
            self, "sell_orders", tuple(sorted(self.sell_orders, key=lambda o: o.price))
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class MarketOrdersDataset(EsiDataset):
    region_id: int
    records: dict[int, BuySellOrders]
    """Represents a collection of market orders indexed by type_id."""


@dataclass(slots=True, kw_only=True, frozen=True)
class MarketOrdersResponse(ResponseMetadata):
    region_id: int


@dataclass(slots=True, kw_only=True, frozen=True)
class OrderSummaryRecord:
    """Represents one side of the market depth for a single item type.

    Scope is repeated on each item so a summary remains meaningful when separated from
    its dataset; source response metadata belongs to the dataset. Monetary values are
    rounded to two decimal places. The depth metrics include every order at or better
    than `five_price`, including all orders tied at that price.
    """

    region_id: int
    type_id: int
    system_id: int | None
    location_id: int | None
    is_buy_summary: bool
    five_price: Decimal
    five_orders: int
    five_items: int
    lowest: Decimal
    highest: Decimal
    total_items: int
    total_orders: int
    average: Decimal
    filtered_items: int
    filtered_orders: int


@dataclass(slots=True, kw_only=True, frozen=True)
class BuySellSummary:
    """Represents the available buy and sell summaries for an item type."""

    buy_summary: OrderSummaryRecord | None
    sell_summary: OrderSummaryRecord | None

    @property
    def buy_5(self) -> Decimal | None:
        """Return the buy-side 5% depth price, if buy orders are available."""
        return self.buy_summary.five_price if self.buy_summary is not None else None

    @property
    def sell_5(self) -> Decimal | None:
        """Return the sell-side 5% depth price, if sell orders are available."""
        return self.sell_summary.five_price if self.sell_summary is not None else None


@dataclass(slots=True, kw_only=True, frozen=True)
class OrderSummaryDataset(EsiDataset):
    """Represents order summaries for a region and optional narrower scope.

    Calculation settings such as the outlier filter factor are input-only and are not
    persisted in the report.
    """

    region_id: int
    system_id: int | None
    location_id: int | None
    records: dict[int, BuySellSummary]

    def iter_summaries(self) -> Iterable[OrderSummaryRecord]:
        """Iterate over all buy and sell summaries in the report."""
        for bs_summary in self.records.values():
            if bs_summary.buy_summary is not None:
                yield bs_summary.buy_summary
            if bs_summary.sell_summary is not None:
                yield bs_summary.sell_summary


@dataclass(slots=True, kw_only=True, frozen=True)
class OrderSummaryResponse(ResponseMetadata):
    """A saved summary scope linked to its source market-order response."""

    order_summary_response_id: int
    region_id: int
    system_id: int | None
    location_id: int | None


@dataclass(slots=True, kw_only=True, frozen=True)
class HistorySummaryRecord:
    """Represents an aggregate market-history summary for one region and item type.

    The summary covers a fixed window of consecutive days and stores the volume-weighted
    price averages for that window along with the average daily order count and volume.
    """

    received_at: str
    """The timestamp when this summary was received."""
    expires_at: str | None
    """The timestamp when this summary expires, if known."""
    argus_expires_at: str | None
    """The timestamp when this summary is considered expired by Argus, if known."""
    region_id: int
    """The region ID associated with this summary."""
    type_id: int
    """The item type ID associated with this summary."""
    start: str
    """The end date of the window as an ISO date string in `YYYY-MM-DD` format."""
    end: str
    """The start date of the window as an ISO date string in `YYYY-MM-DD` format."""
    missing: int
    """The number of dates in the requested window that were missing from the source data."""
    highest: Decimal
    """The volume-weighted average of the daily highest prices in the window."""
    average: Decimal
    """The volume-weighted average of the daily average prices in the window."""
    lowest: Decimal
    """The volume-weighted average of the daily lowest prices in the window."""
    order_count: int
    """The average daily order count across the selected window."""
    volume: Decimal
    """The average daily traded volume across the selected window."""
