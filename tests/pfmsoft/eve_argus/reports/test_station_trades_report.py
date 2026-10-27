"""Contracts for the station-trades collector, renderers, and CLI command."""

import csv
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date
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
from pfmsoft.eve_argus.market_history import util as history_util
from pfmsoft.eve_argus.market_history.models import MarketHistoryRecord
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS, MarketHub
from pfmsoft.eve_argus.reports.station_trades import (
    HistoryWindow,
    RegionalHistory,
    StationTradeRow,
    StationTradesOptions,
    StationTradesReport,
    calculate_history_metrics,
    calculate_unit_economics,
    collect_station_trades,
    evaluate_opportunity,
    is_selected_market_path,
    market_tick,
    proposed_price_targets,
    select_history_window,
)
from pfmsoft.eve_argus.reports.station_trades_render import (
    STATION_TRADES_CSV_COLUMNS,
    render_station_trades_csv,
    render_station_trades_json,
    render_station_trades_markdown,
)
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings
from pfmsoft.eve_argus.static import read as static_read
from pfmsoft.eve_argus.static.models import MarketGroupsDataset, TypesDataset
from pfmsoft.eve_argus.static.store import ManifestEntry, StaticManifest
from pfmsoft.eve_argus.static.util import load_table_definitions

RECEIVED = "2026-10-18T10:00:00Z"
GENERATED = Instant.parse_iso("2026-10-18T12:00:00Z")
GENERATION_DATE = date(2026, 10, 18)
JITA = MARKET_HUBS[0]
ZERO_FEES = StationTradesOptions()
FEES = StationTradesOptions(
    acquisition_broker_fee_percent=Decimal(1),
    sale_broker_fee_percent=Decimal(1),
    sales_tax_percent=Decimal(2),
)

# (type_id, market_group_id, name, published)
TYPES = [
    (34, 18, "Tritanium", 1),
    (35, 18, "Pyerite", 1),
    (40, None, "Nonmarket Thing", 1),
    (100, 10, "Gun | Mk1", 1),
    (101, 11, "Laser", 1),
    (102, 10, "Lonely Buy", 1),
    (103, 10, "Hidden Gun", 0),
    (104, 10, "Crossed", 1),
    (105, 10, "Unknown History", 1),
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
            (
                11,
                "Lasers | Beams",
                "[9, 10, 11]",
                '["Ship Equipment", "Weapons", "Lasers | Beams"]',
            ),
        ],
    )
    connection.executemany(
        """INSERT INTO types
        (type_id, group_id, market_group_id, name, portion_size, published, volume)
        VALUES (?, 1, ?, ?, 1, ?, 1.0)""",
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


# (type_id, is_buy, price, volume_remain, station offset from the hub station)
ORDERS = [
    (34, True, "100.00", 10, 0),
    (34, False, "120.00", 10, 0),
    (34, False, "90.00", 10, 1),
    (34, False, "80.00", 0, 0),
    (35, True, "10.00", 10, 0),
    (35, False, "50.00", 10, 0),
    (40, False, "5.00", 1, 0),
    (100, True, "100.00", 5, 0),
    (100, False, "120.00", 5, 0),
    (101, True, "1000.00", 1, 0),
    (101, False, "2000.00", 1, 0),
    (102, True, "10.00", 1, 0),
    (103, False, "5.00", 1, 0),
    (104, True, "0.01", 1, 0),
    (104, False, "0.02", 1, 0),
    (105, True, "10.00", 1, 0),
    (105, False, "20.00", 1, 0),
]


def orders(
    hub: MarketHub = JITA,
    rows: list[tuple[int, bool, str, int, int]] = ORDERS,
    *,
    expires_at: str | None = "2026-10-18T10:05:00Z",
) -> models.MarketOrdersDataset:
    """Build one regional dataset, including an order at another station."""
    by_type: dict[int, list[models.MarketOrderRecord]] = {}
    for order_id, (type_id, is_buy, price, volume, offset) in enumerate(rows, 1):
        by_type.setdefault(type_id, []).append(
            models.MarketOrderRecord(
                response_metadata_id=7,
                region_id=hub.region_id,
                duration=90,
                is_buy_order=is_buy,
                issued=RECEIVED,
                location_id=hub.station_id + offset,
                min_volume=1,
                order_id=order_id,
                price=Decimal(price),
                range="station",
                system_id=hub.system_id,
                type_id=type_id,
                volume_remain=volume,
                volume_total=max(volume, 1),
            )
        )
    return models.MarketOrdersDataset(
        response_metadata_id=7,
        received_at=RECEIVED,
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


def response(data: models.MarketOrdersDataset) -> models.MarketOrdersResponse:
    """Identify the regional snapshot used for the calculation."""
    return models.MarketOrdersResponse(
        response_metadata_id=data.response_metadata_id,
        received_at=data.received_at,
        expires_at=data.expires_at,
        argus_expires_at=data.argus_expires_at,
        region_id=data.region_id,
    )


WINDOW = select_history_window(
    newest_stored_date="2026-10-17", generation_date=GENERATION_DATE
)


def daily_history(
    type_id: int, *, average: str, volume: int, dates: tuple[str, ...] = WINDOW.dates
) -> tuple[MarketHistoryRecord, ...]:
    """Build one Jita history record per date with constant values."""
    return tuple(
        MarketHistoryRecord(
            received_at="2026-10-18T11:00:00Z",
            expires_at=None,
            argus_expires_at=None,
            region_id=JITA.region_id,
            type_id=type_id,
            average=Decimal(average),
            date=day,
            highest=Decimal(average),
            lowest=Decimal(average),
            order_count=3,
            volume=volume,
        )
        for day in dates
    )


HISTORY = {
    34: daily_history(34, average="110.00", volume=200),
    35: daily_history(35, average="30.00", volume=50),
    100: daily_history(100, average="110.00", volume=100),
    101: daily_history(101, average="1500.00", volume=0)[:1],
    104: daily_history(104, average="0.02", volume=10),
}


def regional_history(
    records: dict[int, tuple[MarketHistoryRecord, ...]] = HISTORY,
    window: HistoryWindow | None = WINDOW,
) -> RegionalHistory:
    """Serve history from memory through the production lookup shape."""
    return RegionalHistory(
        window=window, records=lambda type_id: records.get(type_id, ())
    )


def collect(
    static: Static,
    *,
    options: StationTradesOptions = ZERO_FEES,
    history: RegionalHistory | None = None,
    data: models.MarketOrdersDataset | None = None,
) -> StationTradesReport:
    """Collect the Jita station report with in-memory inputs."""
    data = data or orders()
    return collect_station_trades(
        hub=JITA,
        response=response(data),
        orders=data,
        types=static.types,
        market_groups=static.market_groups,
        history=regional_history() if history is None else history,
        options=options,
        generated_at=GENERATED,
    )


def row(report: StationTradesReport, type_id: int) -> StationTradeRow:
    """Return one report row by type ID."""
    return next(item for item in report.records if item.type_id == type_id)


@pytest.mark.parametrize(
    ("price", "tick"),
    [
        ("0.01", "0.01"),
        ("0.99", "0.01"),
        ("1", "0.01"),
        ("999900", "100"),
        ("1000000", "1000"),
        ("1112000", "1000"),
    ],
)
def test_market_tick(price: str, tick: str) -> None:
    """Ticks use four significant figures with a 0.01 ISK minimum."""
    assert market_tick(Decimal(price)) == Decimal(tick)


@pytest.mark.parametrize(
    ("buy", "sell", "proposed_buy", "proposed_sell", "invalid"),
    [
        ("100", "120", "100.1", "119.9", False),
        ("0.01", "0.02", "0.02", "0.01", True),
        ("100", "0.01", "100.1", None, True),
        ("999900", "1000000", "1000000", "999900", True),
        ("1112000", "1112000", "1113000", "1111000", True),
    ],
)
def test_proposed_price_targets(
    buy: str, sell: str, proposed_buy: str, proposed_sell: str | None, invalid: bool
) -> None:
    """Proposals move one valid tick inside the station spread."""
    result = proposed_price_targets(best_buy=Decimal(buy), best_sell=Decimal(sell))
    assert result == (
        Decimal(proposed_buy),
        None if proposed_sell is None else Decimal(proposed_sell),
        invalid,
    )


def test_unit_economics_worked_example() -> None:
    """Fees are proportional and participation applies once per daily cycle."""
    economics = calculate_unit_economics(
        buy_price=Decimal(100),
        sell_price=Decimal(120),
        regional_daily_volume=Decimal(200),
        options=FEES,
    )
    assert economics.net_profit_per_unit == Decimal("15.4")
    assert economics.estimated_daily_units == Decimal(2)
    assert economics.estimated_daily_net_profit == Decimal("30.8")
    assert economics.modeled_acquisition_capital == Decimal(202)
    assert economics.modeled_sale_listing_cost == Decimal("2.4")
    partial = calculate_unit_economics(
        buy_price=Decimal(100),
        sell_price=Decimal(120),
        regional_daily_volume=Decimal(150),
        options=FEES,
    )
    assert partial.estimated_daily_units == Decimal("1.5")
    assert partial.estimated_daily_net_profit == Decimal("23.10")
    assert partial.one_day_order_units == 1
    assert partial.one_day_order_acquisition_capital == Decimal(101)


@pytest.mark.parametrize(
    ("buy", "sell", "volume", "status"),
    [
        (None, None, None, "missing_buy"),
        ("100", None, None, "missing_sell"),
        ("0.01", "0.02", None, "invalid_price_target"),
        ("100", "120", None, "missing_history"),
        ("100", "120", "0", "zero_history_volume"),
        ("100", "100.2", "10", "invalid_price_target"),
        ("100", "120", "200", "ranked"),
    ],
)
def test_status_precedence(
    buy: str | None, sell: str | None, volume: str | None, status: str
) -> None:
    """Statuses follow the documented precedence."""
    result = evaluate_opportunity(
        best_buy=None if buy is None else Decimal(buy),
        best_sell=None if sell is None else Decimal(sell),
        regional_daily_volume=None if volume is None else Decimal(volume),
        options=ZERO_FEES,
    )
    assert result[0] == status


def test_fees_can_make_a_positive_spread_unprofitable() -> None:
    """A 1% sales tax turns a 0.92 ISK proposed spread into a loss."""
    status, _, _, economics = evaluate_opportunity(
        best_buy=Decimal(100),
        best_sell=Decimal("101.02"),
        regional_daily_volume=Decimal(100),
        options=StationTradesOptions(sales_tax_percent=Decimal(1)),
    )
    assert status == "unprofitable"
    assert economics is not None
    assert economics.net_profit_per_unit == Decimal("-0.11")


@pytest.mark.parametrize(
    "changes",
    [
        {"participation_percent": Decimal(0)},
        {"participation_percent": Decimal(101)},
        {"sales_tax_percent": Decimal(-1)},
        {"sale_broker_fee_percent": Decimal(101)},
    ],
)
def test_invalid_options(changes: dict[str, Decimal]) -> None:
    """Fee rates are 0-100 and participation is greater than 0 and at most 100."""
    with pytest.raises(ValueError):
        StationTradesOptions(**changes)  # type: ignore[arg-type]


def test_history_window_and_metrics() -> None:
    """Absent dates count as zero volume across the full common window."""
    assert WINDOW.newest_date == "2026-10-17"
    assert WINDOW.oldest_date == "2026-10-08"
    assert len(WINDOW.dates) == 10
    with pytest.raises(ValueError, match="strictly before"):
        select_history_window(
            newest_stored_date="2026-10-18", generation_date=GENERATION_DATE
        )
    metrics = calculate_history_metrics(
        records=daily_history(34, average="5", volume=125, dates=WINDOW.dates[:8]),
        region_id=JITA.region_id,
        type_id=34,
        window=WINDOW,
        generation_date=GENERATION_DATE,
    )
    assert metrics.average_daily_volume == Decimal(100)
    assert metrics.missing_days == 2
    assert metrics.freshness == "current"
    assert metrics.newest_date_used == "2026-10-17"


def test_stale_and_inconsistent_history() -> None:
    """History older than seven days is stale; foreign records are rejected."""
    old = select_history_window(
        newest_stored_date="2026-10-09", generation_date=GENERATION_DATE
    )
    records = daily_history(34, average="5", volume=1, dates=old.dates)
    metrics = calculate_history_metrics(
        records=records,
        region_id=JITA.region_id,
        type_id=34,
        window=old,
        generation_date=GENERATION_DATE,
    )
    assert metrics.freshness == "stale"
    with pytest.raises(ValueError, match="inconsistent"):
        calculate_history_metrics(
            records=records,
            region_id=JITA.region_id,
            type_id=35,
            window=old,
            generation_date=GENERATION_DATE,
        )


@pytest.mark.parametrize(
    ("path", "include", "exclude", "selected"),
    [
        ((9, 10), (), (), True),
        ((9, 10), (9,), (), True),
        ((9, 10), (1031,), (), False),
        ((9, 10, 11), (9,), (11,), False),
        ((9, 10), (10,), (10,), False),
    ],
)
def test_market_path_selection(
    path: tuple[int, ...],
    include: tuple[int, ...],
    exclude: tuple[int, ...],
    selected: bool,
) -> None:
    """Subtree match: empty include means all, and exclusions win."""
    assert is_selected_market_path(path, include=include, exclude=exclude) == selected


def test_report_ranks_by_daily_profit_and_scopes_station(static: Static) -> None:
    """Larger daily profit beats margin; other stations and empty orders are ignored."""
    report = collect(static)
    assert [(item.type_id, item.rank) for item in report.ranked] == [
        (34, 1),
        (35, 2),
        (100, 3),
    ]
    tritanium = row(report, 34)
    assert tritanium.best_station_sell_price == Decimal(120)
    assert tritanium.station_sell_order_count == 1
    assert tritanium.proposed_buy_price == Decimal("100.1")
    assert tritanium.proposed_sell_price == Decimal("119.9")
    assert tritanium.economics is not None
    assert tritanium.economics.estimated_daily_net_profit == Decimal("39.6")
    assert tritanium.market_path_names == ("Raw Materials", "Minerals")
    pyerite = row(report, 35)
    assert pyerite.economics is not None
    assert pyerite.economics.net_margin_percent > tritanium.economics.net_margin_percent
    assert {item.type_id: item.status for item in report.records if not item.rank} == {
        101: "zero_history_volume",
        102: "missing_sell",
        104: "invalid_price_target",
        105: "missing_history",
    }
    assert [item.type_id for item in report.records[3:]] == [104, 105, 102, 101]
    assert "missing_history" in row(report, 105).flags
    assert "invalid_price_target" in row(report, 104).flags
    assert "station_sell_book" in row(report, 102).missing_data


def test_report_metadata_flags_and_warnings(static: Static) -> None:
    """Report-wide state is on every row and summarized in warnings."""
    report = collect(static)
    assert report.orders_freshness == "expired"
    assert report.orders_expiry_used == "2026-10-18T10:05:00Z"
    assert report.history_window == WINDOW
    assert report.filtered_out_count == 0
    for item in report.records:
        assert {
            "incomplete_competition_coverage",
            "zero_fee_assumptions",
            "expired_orders",
        } <= set(item.flags)
    text = " ".join(report.warnings)
    assert "station-anchored only" in text
    assert "acquisition_broker_fee_percent" in text
    assert "has expired" in text
    assert "Excluded 2 unpublished or nonmarket" in text
    assert "missing for one or more candidate types" in text


def test_unknown_expiry_and_missing_history_database(static: Static) -> None:
    """No expiry is unknown freshness; no database leaves every row unranked."""
    data = orders(expires_at=None)
    report = collect_station_trades(
        hub=JITA,
        response=response(data),
        orders=data,
        types=static.types,
        market_groups=static.market_groups,
        history=None,
        options=FEES,
        generated_at=GENERATED,
    )
    assert report.orders_freshness == "unknown"
    assert report.history_window is None
    assert not report.ranked
    assert "Market history database is unavailable" in " ".join(report.warnings)
    assert "zero_fee_assumptions" not in report.records[0].flags
    assert "unknown_order_expiry" in report.records[0].flags


def test_market_group_filters_drop_rows(static: Static) -> None:
    """Filtered types are dropped and counted; exclusions win over inclusions."""
    minerals = collect(
        static, options=StationTradesOptions(include_market_group_ids=(1031,))
    )
    assert [item.type_id for item in minerals.records] == [34, 35]
    assert minerals.filtered_out_count == 5
    weapons = collect(
        static,
        options=StationTradesOptions(
            include_market_group_ids=(9,), exclude_market_group_ids=(11,)
        ),
    )
    assert sorted(item.type_id for item in weapons.records) == [100, 102, 104, 105]
    assert weapons.filtered_out_count == 3
    with pytest.raises(ValueError, match="Unknown market group IDs"):
        collect(static, options=StationTradesOptions(include_market_group_ids=(999,)))


def test_empty_snapshot(static: Static) -> None:
    """A station with no active orders produces an empty report."""
    report = collect(static, data=orders(rows=[(34, False, "5.00", 0, 0)]))
    assert report.records == ()
    markdown = render_station_trades_markdown(report)
    assert "No opportunities meet the ranking criteria" in markdown
    assert render_station_trades_csv(report).splitlines() == [
        ",".join(STATION_TRADES_CSV_COLUMNS)
    ]


def test_inconsistent_snapshot_rejected(static: Static) -> None:
    """Orders from another response cannot be mixed into the report."""
    data = orders()
    with pytest.raises(ValueError, match="disagree"):
        collect_station_trades(
            hub=JITA,
            response=models.MarketOrdersResponse(
                response_metadata_id=8,
                received_at=RECEIVED,
                expires_at=data.expires_at,
                argus_expires_at=None,
                region_id=JITA.region_id,
            ),
            orders=data,
            types=static.types,
            market_groups=static.market_groups,
            history=regional_history(),
            options=ZERO_FEES,
            generated_at=GENERATED,
        )


def test_csv_rendering(static: Static) -> None:
    """CSV keeps every row with stable columns, exact decimals, and empty nulls."""
    report = collect(
        static,
        options=StationTradesOptions(
            include_market_group_ids=(9, 1031), exclude_market_group_ids=(11,)
        ),
    )
    rows = list(csv.DictReader(StringIO(render_station_trades_csv(report))))
    assert tuple(rows[0]) == STATION_TRADES_CSV_COLUMNS
    assert len(rows) == len(report.records)
    first = rows[0]
    assert first["type_id"] == "34" and first["rank"] == "1"
    assert first["estimated_daily_net_profit"] == "39.6"
    assert first["include_market_group_ids"] == "9;1031"
    assert first["exclude_market_group_ids"] == "11"
    assert first["market_path"] == "Raw Materials/Minerals"
    missing = next(item for item in rows if item["type_id"] == "105")
    assert missing["rank"] == ""
    assert missing["regional_history_average_price"] == ""
    assert missing["net_profit_per_unit"] == "9.98"
    assert missing["estimated_daily_net_profit"] == ""
    assert missing["status"] == "missing_history"


def test_json_rendering(static: Static) -> None:
    """JSON records provenance, assumptions, filters, and order context."""
    report = collect(
        static, options=StationTradesOptions(exclude_market_group_ids=(10,))
    )
    parsed = json.loads(render_station_trades_json(report))
    assert parsed["schema_version"] == 1
    assert parsed["report"] == "station-trades"
    assert parsed["scope"]["station_id"] == JITA.station_id
    assert parsed["orders"]["freshness"] == "expired"
    assert parsed["history"]["window_start_date"] == "2026-10-08"
    assert parsed["assumptions"]["competition_scope"] == "station_anchored_only"
    assert parsed["filters"] == {
        "include_market_group_ids": [],
        "exclude_market_group_ids": [10],
        "filtered_out_count": 5,
    }
    assert parsed["summary"]["ranked_count"] == 2
    tritanium = parsed["records"][0]
    assert tritanium["economics"]["estimated_daily_net_profit"] == "39.6"
    assert tritanium["station_sell_orders"] == [
        {
            "order_id": 2,
            "price": "120.00",
            "volume_remain": 10,
            "range": "station",
            "min_volume": 1,
        }
    ]


def test_markdown_rendering(static: Static) -> None:
    """Markdown is formatted, escapes pipes, and shows notices and filters."""
    report = collect(
        static, options=StationTradesOptions(include_market_group_ids=(9, 1031))
    )
    markdown = render_station_trades_markdown(report)
    assert format_markdown(markdown) == markdown
    assert "Gun \\| Mk1" in markdown
    assert "**STALE:**" in markdown
    assert "Competition limitation" in markdown
    assert "include 9, 1031; exclude none (0 station types filtered out)" in markdown
    assert "39.60" in markdown
    assert "- **missing_history:** 1" in markdown
    ranked_line = next(line for line in markdown.splitlines() if "Tritanium" in line)
    assert "expired_orders" not in ranked_line


@dataclass(slots=True, kw_only=True)
class Environment:
    """On-disk local inputs exercised through the registered root CLI."""

    settings: EveArgusSettings
    dynamic_path: Path
    history_path: Path


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
    settings.market_history_database = tmp_path / "history.sqlite"
    monkeypatch.setattr(
        "pfmsoft.eve_argus.cli.reports.station_trades.Instant",
        Mock(now=Mock(return_value=GENERATED)),
    )
    monkeypatch.setattr(
        "pfmsoft.eve_argus.eve_argus.EveArgusResources.__aenter__",
        Mock(side_effect=AssertionError("Reports must not initialize ESI resources")),
    )
    return Environment(
        settings=settings,
        dynamic_path=dynamic_path,
        history_path=settings.market_history_database,
    )


def save_orders(env: Environment, *, hubs: list[MarketHub] = MARKET_HUBS) -> None:
    """Store the unit-test order book as each hub's latest regional snapshot."""
    with closing(sqlite3.connect(env.dynamic_path)) as connection:
        for hub in hubs:
            metadata_id = connection.execute(
                "INSERT INTO response_metadata (received_at, expires_at) VALUES (?, ?)",
                (RECEIVED, "2026-10-18T10:05:00Z"),
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
                        ORDERS, 1
                    )
                ],
            )
        connection.commit()


def save_history(env: Environment) -> None:
    """Store Jita history, plus a same-day record the window must ignore."""
    records = [record for items in HISTORY.values() for record in items]
    with closing(sqlite3.connect(env.history_path)) as connection:
        connection.executescript(history_util.load_table_definitions())
        connection.executemany(
            """INSERT INTO market_history
            (received_at, expires_at, region_id, type_id, average, date_, highest,
             lowest, order_count, volume)
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    record.received_at,
                    record.region_id,
                    record.type_id,
                    int(record.average * 100),
                    record.date,
                    int(record.highest * 100),
                    int(record.lowest * 100),
                    record.order_count,
                    record.volume,
                )
                for record in records
            ]
            + [
                (
                    "2026-10-18T11:00:00Z",
                    JITA.region_id,
                    34,
                    100,
                    "2026-10-18",
                    100,
                    100,
                    1,
                    999_999,
                )
            ],
        )
        connection.commit()


def invoke(env: Environment, destination: Path, *args: str) -> Result:
    """Run actual registration, readers, collectors, and renderers."""
    return CliRunner().invoke(
        app,
        ["reports", "station-trades", "--to", str(destination), *args],
        obj={SETTINGS_KEY: env.settings},
    )


def stem(hub: MarketHub) -> str:
    """Return the expected output file stem for a hub."""
    return (
        f"station-trades-{file_safe_string(hub.system_name)}-{hub.station_id}-"
        f"{file_safe_string(RECEIVED)}"
    )


def test_cli_registered_with_options() -> None:
    """The command is registered under reports and exposes its options."""
    runner = CliRunner()
    assert "station-trades" in runner.invoke(app, ["reports", "--help"]).output
    result = runner.invoke(app, ["reports", "station-trades", "--help"])
    assert result.exit_code == 0
    for option in (
        "--to",
        "--overwrite",
        "--quiet",
        "--buy-broker-fee",
        "--sell-broker-fee",
        "--sales-tax",
        "--participation",
        "--include",
        "--exclude",
    ):
        assert option in result.output


def test_cli_writes_all_outputs_with_history(
    environment: Environment, tmp_path: Path
) -> None:
    """History before the generation date drives ranking; options reach outputs."""
    save_orders(environment)
    save_history(environment)
    destination = tmp_path / "reports"
    result = invoke(
        environment,
        destination,
        "--include",
        "1031",
        "--include",
        "9",
        "--exclude",
        "11",
        "--sales-tax",
        "2.5",
    )
    assert result.exit_code == 0, result.output
    assert "Wrote" in result.output
    assert "order snapshot has expired" in result.output
    assert result.output.count("station-anchored only") == 1
    names = sorted(path.name for path in destination.iterdir())
    assert len(names) == 3 * len(MARKET_HUBS)
    for hub in MARKET_HUBS:
        for suffix in ("md", "csv", "json"):
            assert f"{stem(hub)}.{suffix}" in names
    parsed = json.loads((destination / f"{stem(JITA)}.json").read_text())
    assert parsed["history"]["window_end_date"] == "2026-10-17"
    assert parsed["assumptions"]["sales_tax_percent"] == "2.5"
    assert parsed["filters"]["include_market_group_ids"] == [9, 1031]
    assert parsed["filters"]["exclude_market_group_ids"] == [11]
    assert parsed["filters"]["filtered_out_count"] == 1
    assert [item["type_id"] for item in parsed["records"][:3]] == [34, 35, 100]
    assert parsed["records"][0]["history"]["average_daily_volume"] == "200"
    amarr = json.loads((destination / f"{stem(MARKET_HUBS[1])}.json").read_text())
    assert amarr["history"]["window_end_date"] is None
    assert amarr["summary"]["ranked_count"] == 0


def test_cli_without_history_database_warns_and_continues(
    environment: Environment, tmp_path: Path
) -> None:
    """A missing history database warns even when quiet and still writes reports."""
    save_orders(environment)
    destination = tmp_path / "reports"
    result = invoke(environment, destination, "--quiet")
    assert result.exit_code == 0, result.output
    assert "Wrote" not in result.output
    assert "market history database not found" in result.output
    assert "eve-argus fetch market-history --hubs --market-types" in result.output
    assert len(list(destination.iterdir())) == 3 * len(MARKET_HUBS)


def test_cli_missing_orders_writes_nothing(
    environment: Environment, tmp_path: Path
) -> None:
    """Hubs without stored orders fail before any file is written."""
    save_orders(environment, hubs=[JITA])
    destination = tmp_path / "reports"
    result = invoke(environment, destination)
    assert result.exit_code == 1
    assert "No stored regional market orders for: Amarr" in result.output
    assert "eve-argus fetch market-orders --hubs" in result.output
    assert not destination.exists()


def test_cli_existing_outputs_require_overwrite(
    environment: Environment, tmp_path: Path
) -> None:
    """Existing files are protected unless --overwrite is passed."""
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
    assert existing.read_text() != "old"


@pytest.mark.parametrize(
    "args",
    [
        ("--sales-tax", "101"),
        ("--buy-broker-fee", "-1"),
        ("--participation-percent", "0"),
        ("--include", "999"),
        ("--exclude", "not-a-number"),
    ],
)
def test_cli_rejects_bad_options(
    environment: Environment, tmp_path: Path, args: tuple[str, ...]
) -> None:
    """Out-of-range values and unknown market groups are usage errors."""
    save_orders(environment)
    destination = tmp_path / "reports"
    result = invoke(environment, destination, *args)
    assert result.exit_code == 2, result.output
    assert not destination.exists()
