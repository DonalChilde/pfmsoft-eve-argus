from dataclasses import dataclass
from decimal import Decimal


@dataclass(slots=True, kw_only=True, frozen=True)
class MarketHistoryResponse:
    response_metadata_id: int
    received_at: str
    expires_at: str | None
    argus_expires_at: str | None
    region_id: int
    type_id: int


@dataclass(slots=True, kw_only=True, frozen=True)
class MarketHistoryRecord:
    received_at: str
    region_id: int
    type_id: int
    average: Decimal
    date: str
    highest: Decimal
    lowest: Decimal
    order_count: int
    volume: int
