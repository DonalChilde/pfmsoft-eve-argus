"""Contracts for the hub-trades collector, renderers, and CLI command."""

import csv
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, replace
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner, Result
from whenever import Instant

from pfmsoft.eve_argus.cli import app
from pfmsoft.eve_argus.dynamic import models
from pfmsoft.eve_argus.dynamic import util as dynamic_util
from pfmsoft.eve_argus.helpers.file_safe_string import file_safe_string
from pfmsoft.eve_argus.helpers.markdown import format_markdown
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS, MarketHub
from pfmsoft.eve_argus.reports.hub_trades import (
    HubStationBooks,
    HubTradeRow,
    HubTradesOptions,
    HubTradesReport,
    build_station_books,
    collect_hub_trades,
    trade_totals,
    unit_volume_m3,
    walk_books,
)
from pfmsoft.eve_argus.reports.hub_trades_render import (
    HUB_TRADES_CSV_COLUMNS,
    render_hub_trades_csv,
    render_hub_trades_json,
    render_hub_trades_markdown,
)
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings
from pfmsoft.eve_argus.static import read as static_read
from pfmsoft.eve_argus.static.models import MarketGroupsDataset, TypesDataset
from pfmsoft.eve_argus.static.store import ManifestEntry, StaticManifest
from pfmsoft.eve_argus.static.util import load_table_definitions

RECEIVED = "2026-10-18T10:00:00Z"
EXPIRES = "2026-10-18T13:00:00Z"
GENERATED = Instant.parse_iso("2026-10-18T12:00:00Z")
JITA, AMARR, DODIXIE, HEK, RENS = MARKET_HUBS
NO_COSTS = HubTradesOptions()

# (type_id, market_group_id, name, published, volume, packaged_volume)
TYPES = [
    (34, 18, "Tritanium", 1, 0.01, None),
    (35, 18, "Pyerite", 1, 0.01, None),
    (40, None, "Nonmarket Thing", 1, 1.0, None),
    (100, 10, "Gun | Mk1", 1, 5.0, None),
    (101, 11, "Laser", 1, 10.0, 2.0),
    (103, 10, "Hidden Gun", 0, 1.0, None),
    (106, 10, "Ghost", 1, 0.0, None),
]


def populate_static(connection: sqlite3.Connection) -> None:
    """Use production tables and readers for type identity and market paths."""
    connection.executescript(load_table_definitions())
    connection.execute(
        "INSERT INTO categories (category_id, name, published) VALUES (4, 'Stuff', 1)"
    )
    connection.execute(
        """INSERT INTO groups
        (group_id, anchorable, anchored, category_id, fittable_non_singleton,
         name, published, use_base_price)
        VALUES (1, 0, 0, 4, 0, 'Things', 1, 0)"""
    )
    connection.executemany(
        """INSERT INTO market_groups
        (market_group_id, description, has_types, name, int_path, str_path, types)
        VALUES (?, '', 1, ?, ?, ?, '[]')""",
        [
            (1031, "Raw Materials", "[1031]", '["Raw Materials"]'),
            (18, "Minerals", "[1031, 18]", '["Raw Materials", "Minerals"]'),
            (9, "Ship Equipment", "[9]", '["Ship Equipment"]'),
            (10, "Weapons", "[9, 10]", '["Ship Equipment", "Weapons"]'),
            (11, "Lasers", "[9, 10, 11]", '["Ship Equipment", "Weapons", "Lasers"]'),
        ],
    )
    connection.executemany(
        """INSERT INTO types
        (type_id, group_id, market_group_id, name, portion_size, published, volume,
         packaged_volume)
        VALUES (?, 1, ?, ?, 1, ?, ?, ?)""",
        TYPES,
    )
    connection.commit()


@dataclass(slots=True, kw_only=True, frozen=True)
class Static:
    """Real static models read through production readers."""

    types: TypesDataset
    market_groups: MarketGroupsDataset


@pytest.fixture
def static() -> Static:
    """Load static models from an in-memory database."""
    with closing(sqlite3.connect(":memory:")) as connection:
        populate_static(connection)
        return Static(
            types=static_read.types(connection, only_published=False),
            market_groups=static_read.market_groups(connection),
        )


type OrderRow = tuple[int, bool, str, int, int]
"""(type_id, is_buy, price, volume_remain, station offset from the hub station)"""

# Jita sells; the other hubs buy at different prices.
HUB_ORDERS: dict[str, list[OrderRow]] = {
    "Jita": [
        (34, False, "5.00", 100, 0),
        (34, False, "1.00", 100, 1),
        (35, False, "10.00", 10, 0),
        (40, False, "1.00", 1, 0),
        (100, False, "100.00", 2, 0),
        (101, False, "1000.00", 1, 0),
        (103, False, "1.00", 1, 0),
    ],
    "Amarr": [
        (34, True, "7.00", 100, 0),
        (34, True, "100.00", 100, 1),
        (34, True, "90.00", 0, 0),
        (35, True, "10.00", 10, 0),
        (40, True, "5.00", 1, 0),
        (100, True, "150.00", 2, 0),
        (101, True, "1100.00", 1, 0),
        (103, True, "5.00", 1, 0),
    ],
    "Dodixie": [
        (34, True, "6.00", 100, 0),
        (101, True, "1100.00", 1, 0),
    ],
    "Hek": [(34, True, "5.50", 100, 0)],
    "Rens": [],
}


def order(
    order_id: int,
    *,
    is_buy: bool,
    price: str,
    volume: int,
    hub: MarketHub = JITA,
    type_id: int = 34,
    offset: int = 0,
    min_volume: int = 1,
) -> models.MarketOrderRecord:
    """Build one station order."""
    return models.MarketOrderRecord(
        response_metadata_id=hub.region_id,
        region_id=hub.region_id,
        duration=90,
        is_buy_order=is_buy,
        issued=RECEIVED,
        location_id=hub.station_id + offset,
        min_volume=min_volume,
        order_id=order_id,
        price=Decimal(price),
        range="station",
        system_id=hub.system_id,
        type_id=type_id,
        volume_remain=volume,
        volume_total=max(volume, 1),
    )


def books(
    hub: MarketHub,
    rows: list[OrderRow] | None = None,
    *,
    received_at: str = RECEIVED,
    expires_at: str | None = EXPIRES,
) -> HubStationBooks:
    """Build validated station books from one hub's regional snapshot."""
    rows = HUB_ORDERS[hub.system_name] if rows is None else rows
    by_type: dict[int, list[models.MarketOrderRecord]] = {}
    for index, (type_id, is_buy, price, volume, offset) in enumerate(rows, 1):
        by_type.setdefault(type_id, []).append(
            order(
                hub.region_id * 100 + index,
                is_buy=is_buy,
                price=price,
                volume=volume,
                hub=hub,
                type_id=type_id,
                offset=offset,
            )
        )
    response = models.MarketOrdersResponse(
        response_metadata_id=hub.region_id,
        received_at=received_at,
        expires_at=expires_at,
        argus_expires_at=None,
        region_id=hub.region_id,
    )
    dataset = models.MarketOrdersDataset(
        response_metadata_id=hub.region_id,
        received_at=received_at,
        expires_at=expires_at,
        argus_expires_at=None,
        region_id=hub.region_id,
        records={
            type_id: models.BuySellOrders(
                buy_orders=tuple(o for o in items if o.is_buy_order),
                sell_orders=tuple(o for o in items if not o.is_buy_order),
            )
            for type_id, items in by_type.items()
        },
    )
    return build_station_books(hub=hub, response=response, orders=dataset)


def collect(
    static: Static,
    options: HubTradesOptions = NO_COSTS,
    *,
    source: HubStationBooks | None = None,
    destinations: list[HubStationBooks] | None = None,
) -> HubTradesReport:
    """Collect Jita's trades to the other hubs."""
    return collect_hub_trades(
        source=source or books(JITA),
        destinations=destinations
        if destinations is not None
        else [books(hub) for hub in MARKET_HUBS[1:]],
        types=static.types,
        market_groups=static.market_groups,
        options=options,
        generated_at=GENERATED,
    )


def route(report: HubTradesReport, type_id: int, system: str) -> HubTradeRow:
    """Return one route row."""
    matches = [
        row
        for row in report.records
        if row.type_id == type_id and row.destination_system_name == system
    ]
    assert len(matches) == 1
    return matches[0]


# --- Walk and totals ----------------------------------------------------------

EXAMPLE_SELLS = [
    order(1, is_buy=False, price="100", volume=10),
    order(2, is_buy=False, price="105", volume=10),
]
EXAMPLE_BUYS = [
    order(3, is_buy=True, price="120", volume=5),
    order(4, is_buy=True, price="110", volume=20),
]


def test_walk_worked_example_with_transport() -> None:
    """Both books are walked until source supply runs out."""
    options = HubTradesOptions(transport_per_m3=Decimal(1))
    walk = walk_books(
        sells=reversed(EXAMPLE_SELLS),
        buys=reversed(EXAMPLE_BUYS),
        m3_per_unit=Decimal(1),
        options=options,
    )
    assert [
        (f.source_order_id, f.destination_order_id, f.quantity) for f in walk.fills
    ] == [
        (1, 3, 5),
        (1, 4, 5),
        (2, 4, 10),
    ]
    assert walk.limit_reason == "source_supply"
    assert not walk.min_volume_skipped
    totals = trade_totals(fills=walk.fills, m3_per_unit=Decimal(1), options=options)
    assert totals.units == 20
    assert totals.total_m3 == 20
    assert totals.purchase_cost == 2050
    assert totals.gross_revenue == 2250
    assert totals.sales_tax == 0
    assert totals.transport_cost == 20
    assert totals.net_profit == 180
    assert totals.net_margin_percent == Decimal(180) / 2050 * 100
    assert totals.profit_per_m3 == 9
    assert (totals.last_sell_price, totals.last_buy_price) == (105, 110)
    assert totals.average_sell_price == Decimal("102.5")
    assert totals.average_buy_price == Decimal("112.5")
    assert (totals.source_order_count, totals.destination_order_count) == (2, 2)


def test_walk_worked_example_with_tax_exhausts_profit() -> None:
    """Sales tax stops the walk when the next unit would lose money."""
    options = HubTradesOptions(
        sales_tax_percent=Decimal(4), transport_per_m3=Decimal(1)
    )
    walk = walk_books(
        sells=EXAMPLE_SELLS, buys=EXAMPLE_BUYS, m3_per_unit=Decimal(1), options=options
    )
    assert walk.limit_reason == "profit_exhausted"
    totals = trade_totals(fills=walk.fills, m3_per_unit=Decimal(1), options=options)
    assert totals.units == 10
    assert totals.purchase_cost == 1000
    assert totals.gross_revenue == 1150
    assert totals.sales_tax == 46
    assert totals.transport_cost == 10
    assert totals.net_profit == 94
    assert [fill.net_profit_per_unit for fill in walk.fills] == [
        Decimal("14.2"),
        Decimal("4.6"),
    ]


def test_walk_limited_by_destination_demand() -> None:
    """The walk stops when destination buy orders are filled."""
    walk = walk_books(
        sells=EXAMPLE_SELLS,
        buys=EXAMPLE_BUYS[:1],
        m3_per_unit=Decimal(1),
        options=NO_COSTS,
    )
    assert walk.limit_reason == "destination_demand"
    assert sum(fill.quantity for fill in walk.fills) == 5


def test_walk_without_profitable_unit_has_no_fills() -> None:
    """Costs can erase a positive price spread."""
    walk = walk_books(
        sells=[order(1, is_buy=False, price="100", volume=1)],
        buys=[order(2, is_buy=True, price="101", volume=1)],
        m3_per_unit=Decimal(2),
        options=HubTradesOptions(transport_per_m3=Decimal(1)),
    )
    assert walk.fills == ()
    assert walk.limit_reason == "profit_exhausted"


def test_walk_skips_buy_whose_min_volume_cannot_be_met() -> None:
    """A buy order needing more profitable supply than exists is skipped."""
    walk = walk_books(
        sells=[order(1, is_buy=False, price="100", volume=3)],
        buys=[
            order(2, is_buy=True, price="200", volume=10, min_volume=5),
            order(3, is_buy=True, price="150", volume=3),
        ],
        m3_per_unit=Decimal(1),
        options=NO_COSTS,
    )
    assert walk.min_volume_skipped
    assert [(f.destination_order_id, f.quantity) for f in walk.fills] == [(3, 3)]


def test_trade_totals_require_fills() -> None:
    """Totals of an empty walk are rejected."""
    with pytest.raises(ValueError, match="at least one fill"):
        trade_totals(fills=(), m3_per_unit=None, options=NO_COSTS)


def test_unit_volume_prefers_packaged(static: Static) -> None:
    """Packaged volume wins; unusable volumes are unknown."""
    assert unit_volume_m3(static.types[101]) == Decimal(2)
    assert unit_volume_m3(static.types[34]) == Decimal("0.01")
    assert unit_volume_m3(static.types[106]) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"sales_tax_percent": Decimal(-1)},
        {"sales_tax_percent": Decimal(101)},
        {"transport_per_m3": Decimal(-1)},
        {"min_profit": Decimal("NaN")},
    ],
)
def test_invalid_options(changes: dict[str, Decimal]) -> None:
    """Out-of-range settings are rejected."""
    with pytest.raises(ValueError):
        HubTradesOptions(**changes)


# --- Collection ---------------------------------------------------------------


def test_report_ranks_routes_and_marks_best_matches(static: Static) -> None:
    """Rows rank by net profit, then profit per m³; best matches are marked."""
    report = collect(static)
    ranked = [(row.type_id, row.destination_system_name) for row in report.ranked]
    assert ranked == [
        (34, "Amarr"),
        (34, "Dodixie"),
        (101, "Amarr"),
        (101, "Dodixie"),
        (100, "Amarr"),
        (34, "Hek"),
    ]
    assert [row.rank for row in report.ranked] == [1, 2, 3, 4, 5, 6]
    tritanium = route(report, 34, "Amarr")
    assert tritanium.totals is not None
    assert tritanium.totals.net_profit == 200
    assert tritanium.totals.total_m3 == 1
    assert tritanium.is_best_match
    assert tritanium.destination_match_count == 3
    assert tritanium.alternate_destinations == ("Dodixie", "Hek")
    hek = route(report, 34, "Hek")
    assert not hek.is_best_match
    assert hek.best_match_destination == "Amarr"
    assert hek.destination_match_count == 3
    # Equal profit and m³: the earlier hub wins the tie.
    assert route(report, 101, "Amarr").is_best_match
    assert not route(report, 101, "Dodixie").is_best_match
    assert route(report, 100, "Amarr").destination_match_count == 1
    best = report.best_matches
    assert [row.type_id for row in best] == [34, 101, 100]
    multi = report.multi_destination_items
    assert [(item.best.type_id, len(item.alternates)) for item in multi] == [
        (34, 2),
        (101, 1),
    ]


def test_report_scopes_station_and_counts_candidates(static: Static) -> None:
    """Other stations, exhausted orders, and nonmarket types are excluded."""
    report = collect(static)
    tritanium = route(report, 34, "Amarr")
    assert tritanium.best_sell_price == 5
    assert tritanium.best_buy_price == 7
    assert tritanium.source_available_units == 100
    assert report.no_overlap_count == 1
    assert report.status_counts == {"no_overlap": 1, "ranked": 6}
    assert {row.type_id for row in report.records}.isdisjoint({35, 40, 103})
    assert any("Excluded 2 unpublished or nonmarket" in w for w in report.warnings)
    assert report.source.freshness == "current"
    assert report.snapshot_spread_seconds == 0
    assert "Rens" in [item.hub.system_name for item in report.destinations]


def test_min_profit_moves_rows_below_threshold(static: Static) -> None:
    """Rows at or below the minimum profit are kept but not ranked."""
    report = collect(static, HubTradesOptions(min_profit=Decimal(100)))
    assert [row.type_id for row in report.ranked] == [34]
    assert report.status_counts["below_min_profit"] == 5
    assert route(report, 34, "Amarr").destination_match_count == 1
    assert route(report, 101, "Amarr").rank is None


def test_costs_reduce_profit_and_create_no_overlap(static: Static) -> None:
    """Transport is charged per m³ and tax per gross revenue."""
    options = HubTradesOptions(
        sales_tax_percent=Decimal(10), transport_per_m3=Decimal(10)
    )
    report = collect(static, options)
    totals = route(report, 34, "Amarr").totals
    assert totals is not None
    assert totals.sales_tax == 70
    assert totals.transport_cost == 10
    assert totals.net_profit == Decimal("120")
    # Hek: 5.50 x 0.9 - 5 - 0.1 < 0; Dodixie: 6 x 0.9 - 5 - 0.1 > 0.
    assert [
        row.destination_system_name for row in report.records if row.type_id == 34
    ] == [
        "Amarr",
        "Dodixie",
    ]
    # Pyerite, Gun, Laser twice, and Tritanium to Hek lose money.
    assert report.no_overlap_count == 5
    assert "zero_sales_tax" not in route(report, 34, "Amarr").flags


def test_unknown_volume_depends_on_transport_rate(static: Static) -> None:
    """Unknown m³ ranks with free transport but is not evaluated otherwise."""
    source = books(JITA, [(106, False, "10", 1, 0)])
    destinations = [books(AMARR, [(106, True, "20", 1, 0)])]
    free = collect(static, source=source, destinations=destinations)
    row = route(free, 106, "Amarr")
    assert row.status == "ranked"
    assert "unknown_volume" in row.flags
    assert row.totals is not None
    assert row.totals.total_m3 is None
    assert row.totals.profit_per_m3 is None
    paid = collect(
        static,
        HubTradesOptions(transport_per_m3=Decimal(1)),
        source=source,
        destinations=destinations,
    )
    row = route(paid, 106, "Amarr")
    assert row.status == "unknown_volume"
    assert row.totals is None
    assert row.fills == ()
    assert any("unknown m³" in warning for warning in paid.warnings)


@pytest.mark.parametrize(
    ("received", "gap"),
    [("2026-10-18T10:30:00Z", False), ("2026-10-18T10:31:00Z", True)],
)
def test_snapshot_spread_warning(static: Static, received: str, gap: bool) -> None:
    """Snapshots received more than 30 minutes apart are flagged."""
    report = collect(static, destinations=[books(AMARR, received_at=received)])
    assert ("snapshot_age_gap" in route(report, 34, "Amarr").flags) is gap
    assert any("minutes apart" in warning for warning in report.warnings) is gap


def test_destination_freshness_flags(static: Static) -> None:
    """Stale or unknown destination snapshots flag their rows and warn."""
    report = collect(
        static,
        destinations=[
            books(AMARR, expires_at="2026-10-18T11:00:00Z"),
            books(DODIXIE, expires_at=None),
        ],
    )
    assert "expired_destination_orders" in route(report, 34, "Amarr").flags
    assert "unknown_destination_expiry" in route(report, 34, "Dodixie").flags
    assert any("Amarr order snapshot has expired" in w for w in report.warnings)
    assert any("Dodixie order snapshot has unknown" in w for w in report.warnings)


@pytest.mark.parametrize(
    ("options", "types", "filtered"),
    [
        (HubTradesOptions(exclude_market_group_ids=(11,)), {34, 100}, 1),
        (HubTradesOptions(include_market_group_ids=(1031,)), {34}, 2),
        (
            HubTradesOptions(
                include_market_group_ids=(9,), exclude_market_group_ids=(10,)
            ),
            set(),
            4,
        ),
    ],
)
def test_market_group_filters(
    static: Static, options: HubTradesOptions, types: set[int], filtered: int
) -> None:
    """Filters apply to market-group subtrees and count filtered types once."""
    report = collect(static, options)
    assert {row.type_id for row in report.records} == types
    assert report.filtered_out_count == filtered


def test_unknown_market_group_filter_rejected(static: Static) -> None:
    """Unknown filter IDs fail before collection."""
    with pytest.raises(ValueError):
        collect(static, HubTradesOptions(include_market_group_ids=(999,)))


def test_duplicate_destinations_rejected(static: Static) -> None:
    """The source may not also be a destination."""
    with pytest.raises(ValueError, match="distinct"):
        collect(static, destinations=[books(AMARR), books(JITA)])


# --- Rendering ----------------------------------------------------------------


def test_csv_rendering(static: Static) -> None:
    """CSV has the declared header, plain decimals, and empty unknowns."""
    report = collect(static)
    rows = list(csv.DictReader(StringIO(render_hub_trades_csv(report))))
    assert tuple(rows[0]) == HUB_TRADES_CSV_COLUMNS
    assert len(rows) == len(report.records)
    first = rows[0]
    assert first["type_name"] == "Tritanium"
    assert first["destination_system_name"] == "Amarr"
    assert first["is_best_match"] == "true"
    assert first["alternate_destinations"] == "Dodixie;Hek"
    assert first["net_profit"] == "200.00"
    assert first["total_m3"] == "1.00"
    assert first["source_orders_freshness"] == "current"
    assert rows[1]["is_best_match"] == "false"
    assert rows[1]["best_match_destination"] == "Amarr"
    unknown = collect(
        static,
        HubTradesOptions(transport_per_m3=Decimal(1)),
        source=books(JITA, [(106, False, "10", 1, 0)]),
        destinations=[books(AMARR, [(106, True, "20", 1, 0)])],
    )
    row = next(csv.DictReader(StringIO(render_hub_trades_csv(unknown))))
    assert row["m3_per_unit"] == ""
    assert row["net_profit"] == ""
    assert row["rank"] == ""


def test_json_rendering(static: Static) -> None:
    """JSON keeps fills, summary totals over best matches, and provenance."""
    report = collect(static)
    payload = json.loads(render_hub_trades_json(report))
    assert payload["report"] == "hub-trades"
    assert payload["schema_version"] == 1
    assert payload["source"]["system_name"] == "Jita"
    assert payload["source"]["response_metadata_id"] == JITA.region_id
    assert len(payload["destinations"]) == 4
    summary = payload["summary"]
    assert summary["ranked_count"] == 6
    assert summary["best_match_item_count"] == 3
    assert summary["multi_destination_item_count"] == 2
    assert Decimal(summary["best_match_total_net_profit"]) == 400
    assert Decimal(summary["best_match_total_m3"]) == 13
    assert summary["status_counts"] == {"no_overlap": 1, "ranked": 6}
    first = payload["records"][0]
    assert first["fills"][0]["quantity"] == 100
    assert first["totals"]["net_profit"] == "200.00"
    assert payload["assumptions"]["transport_per_m3"] == "0"


def test_markdown_rendering(static: Static) -> None:
    """Markdown is formatted, escaped, and agrees with the other formats."""
    report = collect(static)
    markdown = render_hub_trades_markdown(report)
    assert format_markdown(markdown) == markdown
    assert "# Hub Trades from Jita" in markdown
    assert "Gun \\| Mk1" in markdown
    assert "Tritanium (`34`): best Amarr 200.00 ISK (1 m³); also Dodixie" in markdown
    assert "Amarr (+2)" in markdown
    assert "★" in markdown
    assert "**no\\_overlap:** 1" in markdown or "**no_overlap:** 1" in markdown
    assert "transport is 0 ISK/m³" in markdown
    assert "Snapshot age gap" not in markdown
    best_row = next(
        line
        for line in markdown.splitlines()
        if line.startswith("|") and line.split("|")[1].strip() == "1"
    )
    assert "Amarr" in best_row
    assert "400.00" in markdown


def test_markdown_limits_rows_and_handles_empty(static: Static) -> None:
    """An empty report renders a placeholder row."""
    report = collect(static, destinations=[books(RENS)])
    markdown = render_hub_trades_markdown(report)
    assert "No trades meet the ranking criteria" in markdown
    assert format_markdown(markdown) == markdown
    many = replace(report, records=collect(static).records * 20)
    assert "Showing 100 of 120 ranked rows" in render_hub_trades_markdown(many)


# --- CLI ----------------------------------------------------------------------


@dataclass(slots=True, kw_only=True)
class Environment:
    """On-disk local inputs exercised through the registered root CLI."""

    settings: EveArgusSettings
    dynamic_path: Path


@pytest.fixture
def environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Environment:
    """Set up real databases, fix the clock, and forbid network initialization."""
    dynamic_path = tmp_path / "dynamic.sqlite"
    static_path = tmp_path / "static.sqlite"
    with closing(sqlite3.connect(dynamic_path)) as connection:
        connection.executescript(dynamic_util.load_table_definitions())
    with closing(sqlite3.connect(static_path)) as connection:
        populate_static(connection)
    (tmp_path / "manifest.json").write_text(
        StaticManifest(
            entries={
                1: ManifestEntry(
                    build_number=1,
                    release_date="2026-10-17",
                    file_name=static_path.name,
                )
            }
        ).serialize()
    )
    settings = Mock(spec=EveArgusSettings)
    settings.static_database_store = tmp_path
    settings.static_database_build_number = None
    settings.argus_dynamic_database = dynamic_path
    monkeypatch.setattr(
        "pfmsoft.eve_argus.cli.reports.hub_trades.Instant",
        Mock(now=Mock(return_value=GENERATED)),
    )
    monkeypatch.setattr(
        "pfmsoft.eve_argus.eve_argus.EveArgusResources.__aenter__",
        Mock(side_effect=AssertionError("Reports must not initialize ESI resources")),
    )
    return Environment(settings=settings, dynamic_path=dynamic_path)


def save_orders(env: Environment, *, hubs: list[MarketHub] = MARKET_HUBS) -> None:
    """Store each hub's order book as its latest regional snapshot."""
    with closing(sqlite3.connect(env.dynamic_path)) as connection:
        for hub in hubs:
            metadata_id = connection.execute(
                "INSERT INTO response_metadata (received_at, expires_at) VALUES (?, ?)",
                (RECEIVED, EXPIRES),
            ).lastrowid
            connection.execute(
                """INSERT INTO get_markets_region_id_orders_response
                (response_metadata_id, region_id, received_at) VALUES (?, ?, ?)""",
                (metadata_id, hub.region_id, RECEIVED),
            )
            connection.executemany(
                """
                INSERT INTO market_orders (
                    response_metadata_id, region_id, duration, is_buy_order,
                    issued, location_id, min_volume, order_id, price, range_,
                    system_id, type_id, volume_remain, volume_total
                ) VALUES (?, ?, 90, ?, ?, ?, 1, ?, ?, 'station', ?, ?, ?, ?)
                """,
                [
                    (
                        metadata_id,
                        hub.region_id,
                        is_buy,
                        RECEIVED,
                        hub.station_id + offset,
                        hub.region_id * 100 + order_id,
                        int(Decimal(price) * 100),
                        hub.system_id,
                        type_id,
                        volume,
                        max(volume, 1),
                    )
                    for order_id, (type_id, is_buy, price, volume, offset) in enumerate(
                        HUB_ORDERS[hub.system_name], 1
                    )
                ],
            )
        connection.commit()


def invoke(env: Environment, destination: Path, *args: str) -> Result:
    """Run actual registration, readers, collectors, and renderers."""
    return CliRunner().invoke(
        app,
        ["reports", "hub-trades", "--to", str(destination), *args],
        obj={SETTINGS_KEY: env.settings},
    )


def stem(hub: MarketHub) -> str:
    """Return the expected output file stem for a source hub."""
    return (
        f"hub-trades-from-{file_safe_string(hub.system_name)}-{hub.station_id}-"
        f"{file_safe_string(GENERATED.format_iso())}"
    )


def test_cli_registered_with_options() -> None:
    """The command is registered under reports and exposes its options."""
    runner = CliRunner()
    assert "hub-trades" in runner.invoke(app, ["reports", "--help"]).output
    result = runner.invoke(app, ["reports", "hub-trades", "--help"])
    assert result.exit_code == 0
    for option in (
        "--to",
        "--overwrite",
        "--quiet",
        "--sales-tax",
        "--transport-per-m3",
        "--min-profit",
        "--include",
        "--exclude",
    ):
        assert option in result.output


def test_cli_writes_all_outputs(environment: Environment, tmp_path: Path) -> None:
    """Every hub is a source; options reach the outputs."""
    save_orders(environment)
    destination = tmp_path / "reports"
    result = invoke(
        environment,
        destination,
        "--exclude",
        "11",
        "--sales-tax",
        "2.5",
        "--transport-per-m3",
        "0.5",
    )
    assert result.exit_code == 0, result.output
    assert "Wrote" in result.output
    assert result.output.count("primary station are matched") == 1
    names = sorted(path.name for path in destination.iterdir())
    assert len(names) == 3 * len(MARKET_HUBS)
    for hub in MARKET_HUBS:
        for suffix in ("md", "csv", "json"):
            assert f"{stem(hub)}.{suffix}" in names
    parsed = json.loads((destination / f"{stem(JITA)}.json").read_text())
    assert parsed["assumptions"]["sales_tax_percent"] == "2.5"
    assert parsed["assumptions"]["transport_per_m3"] == "0.5"
    assert parsed["filters"]["exclude_market_group_ids"] == [11]
    assert parsed["filters"]["filtered_out_count"] == 1
    assert parsed["records"][0]["type_id"] == 34
    assert parsed["records"][0]["destination_system_name"] == "Amarr"
    amarr = json.loads((destination / f"{stem(AMARR)}.json").read_text())
    assert amarr["summary"]["ranked_count"] == 0
    rows = list(
        csv.DictReader(StringIO((destination / f"{stem(JITA)}.csv").read_text()))
    )
    assert (
        rows[0]["destination_system_name"]
        == parsed["records"][0]["destination_system_name"]
    )


def test_cli_quiet_keeps_warnings(environment: Environment, tmp_path: Path) -> None:
    """Quiet suppresses progress but not data warnings."""
    save_orders(environment)
    result = invoke(environment, tmp_path / "reports", "--quiet")
    assert result.exit_code == 0, result.output
    assert "Wrote" not in result.output
    assert "Warning [" in result.output


def test_cli_missing_orders_writes_nothing(
    environment: Environment, tmp_path: Path
) -> None:
    """A missing hub snapshot fails before any output is written."""
    save_orders(environment, hubs=MARKET_HUBS[:-1])
    destination = tmp_path / "reports"
    result = invoke(environment, destination)
    assert result.exit_code == 1
    assert "Rens" in result.output
    assert "fetch market-orders" in result.output
    assert not destination.exists()


def test_cli_existing_outputs_require_overwrite(
    environment: Environment, tmp_path: Path
) -> None:
    """Existing reports are protected unless --overwrite is given."""
    save_orders(environment)
    destination = tmp_path / "reports"
    destination.mkdir()
    existing = destination / f"{stem(JITA)}.md"
    existing.write_text("old")
    result = invoke(environment, destination)
    assert result.exit_code == 1
    assert "already exists" in result.output
    assert existing.read_text() == "old"
    assert len(list(destination.iterdir())) == 1
    result = invoke(environment, destination, "--overwrite")
    assert result.exit_code == 0, result.output
    assert existing.read_text().startswith("# Hub Trades from Jita")


@pytest.mark.parametrize(
    "args",
    [
        ("--sales-tax", "101"),
        ("--transport-per-m3", "-1"),
        ("--min-profit", "-1"),
        ("--include", "999"),
    ],
)
def test_cli_rejects_bad_options(
    environment: Environment, tmp_path: Path, args: tuple[str, str]
) -> None:
    """Invalid options exit with a usage error and write nothing."""
    save_orders(environment)
    destination = tmp_path / "reports"
    result = invoke(environment, destination, *args)
    assert result.exit_code == 2, result.output
    assert not destination.exists()
