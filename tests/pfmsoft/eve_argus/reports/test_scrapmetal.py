"""Contracts for scrapmetal reprocessing deal and price-point collection/rendering."""

import csv
import json
import re
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
from pfmsoft.eve_argus.dynamic.order_summary import calculate_dataset_summaries
from pfmsoft.eve_argus.helpers.file_safe_string import file_safe_string
from pfmsoft.eve_argus.market_history import util as history_util
from pfmsoft.eve_argus.market_history.models import HistorySummaryRecord
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS, MarketHub
from pfmsoft.eve_argus.reports import scrapmetal
from pfmsoft.eve_argus.reports.scrapmetal import (
    HubPriceInputs,
    ScrapmetalDealRow,
    ScrapmetalOptions,
    collect_scrapmetal_deals,
    collect_scrapmetal_price_points,
    eligible_input_ids,
    recovered_quantity,
)
from pfmsoft.eve_argus.reports.scrapmetal_render import (
    render_scrapmetal_deals_csv,
    render_scrapmetal_deals_json,
    render_scrapmetal_deals_markdown,
    render_scrapmetal_price_points_csv,
    render_scrapmetal_price_points_json,
)
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings
from pfmsoft.eve_argus.static import read as static_read
from pfmsoft.eve_argus.static.models import (
    MarketGroupsDataset,
    TypeMaterialsDataset,
    TypesDataset,
)
from pfmsoft.eve_argus.static.store import ManifestEntry, StaticManifest
from pfmsoft.eve_argus.static.util import load_table_definitions

RECEIVED = "2026-10-18T10:00:00Z"
GENERATED = Instant.parse_iso("2026-10-18T12:00:00Z")
JITA = MARKET_HUBS[0]
AMARR = MARKET_HUBS[1]
OPTIONS = ScrapmetalOptions(min_profit=Decimal(100), max_slippage=Decimal(20))

# (type_id, market_group_id, name, portion_size, published, volume, packaged_volume)
TYPES = [
    (34, 18, "Tritanium", 1, 1, 0.01, None),
    (35, 18, "Pyerite", 1, 1, 0.01, None),
    (36, 18, "Mexallon", 1, 1, 0.01, None),
    (40, None, "Unmarketable Salvage", 1, 1, 0.01, None),
    (100, 10, "Scrap | Gun", 1, 1, 10.0, 5.0),
    (101, 10, "Ammo Pack", 100, 1, 0.01, None),
    (102, 18, "Ore Chunk", 1, 1, 1.0, None),
    (103, 10, "Hidden Gun", 1, 0, 5.0, None),
    (104, 10, "Plain Item", 1, 1, 5.0, None),
    (105, 10, "Salvaged Gun", 1, 1, 5.0, None),
    (106, 10, "Tiny Item", 1, 1, 5.0, None),
]
# (type_id, material_type_id, quantity)
MATERIALS = [
    (100, 34, 200),
    (100, 35, 20),
    (101, 34, 10),
    (102, 34, 100),
    (103, 34, 100),
    (105, 34, 100),
    (105, 40, 10),
    (106, 36, 1),
]


def populate_static(connection: sqlite3.Connection) -> None:
    """Use production tables/readers for eligibility, materials, and market paths."""
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
        ],
    )
    connection.executemany(
        """INSERT INTO types
        (type_id, group_id, market_group_id, name, portion_size, published, volume,
         packaged_volume)
        VALUES (?, 1, ?, ?, ?, ?, ?, ?)""",
        TYPES,
    )
    connection.executemany(
        "INSERT INTO type_materials (type_id) VALUES (?)",
        sorted({(type_id,) for type_id, _, _ in MATERIALS}),
    )
    connection.executemany(
        """INSERT INTO type_material_components (type_id, material_type_id, quantity)
        VALUES (?, ?, ?)""",
        MATERIALS,
    )
    connection.commit()


@dataclass(slots=True, kw_only=True, frozen=True)
class Static:
    """Real static models read through production readers."""

    types: TypesDataset
    type_materials: TypeMaterialsDataset
    market_groups: MarketGroupsDataset


@pytest.fixture
def static() -> Static:
    """Load static models from an in-memory database."""
    with closing(sqlite3.connect(":memory:")) as connection:
        populate_static(connection)
        return Static(
            types=static_read.types(connection, only_published=False),
            type_materials=static_read.type_materials(connection),
            market_groups=static_read.market_groups(connection),
        )


# (type_id, is_buy, price, volume_remain, in hub system)
ORDERS = [
    (100, False, "50.00", 2, True),
    (100, False, "100.00", 3, True),
    (100, False, "200.00", 5, True),
    (100, False, "1.00", 50, False),
    (101, False, "0.01", 150, True),
    (102, False, "0.01", 1000, True),
    (103, False, "0.01", 1000, True),
    (105, False, "10.00", 1, True),
    (34, True, "1.00", 150, True),
    (34, True, "0.50", 1000, True),
    (34, False, "1.10", 1000, True),
    (35, True, "2.00", 100, True),
    (35, False, "2.20", 100, True),
]


def orders(
    hub: MarketHub = JITA, rows: list[tuple[int, bool, str, int, bool]] = ORDERS
) -> models.MarketOrdersDataset:
    """Build a regional dataset, including an order outside the hub system."""
    by_type: dict[int, list[models.MarketOrderRecord]] = {}
    for order_id, (type_id, is_buy, price, volume, in_hub) in enumerate(rows, 1):
        by_type.setdefault(type_id, []).append(
            models.MarketOrderRecord(
                response_metadata_id=7,
                region_id=hub.region_id,
                duration=90,
                is_buy_order=is_buy,
                issued=RECEIVED,
                location_id=hub.station_id,
                min_volume=1,
                order_id=order_id,
                price=Decimal(price),
                range="station",
                system_id=hub.system_id if in_hub else hub.system_id + 1,
                type_id=type_id,
                volume_remain=volume,
                volume_total=volume,
            )
        )
    return models.MarketOrdersDataset(
        response_metadata_id=7,
        received_at=RECEIVED,
        expires_at="2026-10-18T10:05:00Z",
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


def history(
    type_id: int,
    *,
    average: str = "60.00",
    volume: str = "1",
    newest: str = "2026-10-17",
) -> HistorySummaryRecord:
    """Build a 10-day summary; `start` is the newest date in the window."""
    return HistorySummaryRecord(
        received_at=RECEIVED,
        expires_at=None,
        argus_expires_at=None,
        region_id=JITA.region_id,
        type_id=type_id,
        start=newest,
        end="2026-10-01",
        missing=1,
        highest=Decimal(average),
        average=Decimal(average),
        lowest=Decimal(average),
        order_count=3,
        volume=Decimal(volume),
    )


def deals(
    static: Static,
    *,
    options: ScrapmetalOptions = OPTIONS,
    history_records: dict[int, HistorySummaryRecord] | None = None,
    data: models.MarketOrdersDataset | None = None,
) -> scrapmetal.ScrapmetalHubReport:
    """Collect Jita deals with optional in-memory history."""
    data = data or orders()
    return collect_scrapmetal_deals(
        hub=JITA,
        response=response(data),
        orders=data,
        summaries=calculate_dataset_summaries(data, system_id=JITA.system_id),
        types=static.types,
        type_materials=static.type_materials,
        market_groups=static.market_groups,
        history=None if history_records is None else history_records.get,
        options=options,
        generated_at=GENERATED,
    )


def row(
    report: scrapmetal.ScrapmetalHubReport, type_id: int, scenario: str
) -> ScrapmetalDealRow:
    """Find one deal row by input type and scenario."""
    return next(
        item
        for item in report.records
        if item.type_id == type_id and item.scenario == scenario
    )


def test_recovered_quantity_rounds_down() -> None:
    """Fractional recovered units are lost, including fractional yields."""
    assert recovered_quantity(200, Decimal(55)) == 110
    assert recovered_quantity(1, Decimal(55)) == 0
    assert recovered_quantity(10, Decimal("54.5")) == 5


def test_eligible_inputs(static: Static) -> None:
    """Keep published market items with fixed, non-raw-material reprocessing output."""
    assert eligible_input_ids(
        types=static.types,
        type_materials=static.type_materials,
        market_groups=static.market_groups,
    ) == [100, 101, 105, 106]


@pytest.mark.parametrize(
    "changes",
    [
        {"yield_percent": Decimal(101)},
        {"sales_tax": Decimal(-1)},
        {"broker_fee": Decimal(100.5)},
        {"reprocessing_tax": Decimal(-0.1)},
        {"min_profit": Decimal(-1)},
        {"min_margin": Decimal(-1)},
        {"max_slippage": Decimal(-1)},
    ],
)
def test_invalid_options(changes: dict[str, Decimal]) -> None:
    """Reject rates outside 0-100 and negative thresholds."""
    with pytest.raises(ValueError):
        replace(OPTIONS, **changes)


def test_immediate_walk_sizes_the_profitable_portion_count(static: Static) -> None:
    """Walk cheapest input first, and walk material buy books down per portion."""
    report = deals(static)
    gun = row(report, 100, "sell_to_buy_orders")
    # Portion 1: 110 trit @1.00 + 11 pye @2.00 = 132 for 50.
    # Portion 2: 40 @1.00 + 70 @0.50 + 22 = 97 for 50.
    # Portion 3: 110 @0.50 + 22 = 77 for 100, a loss.
    assert gun.status == "profitable"
    assert gun.rank == 1
    assert (gun.portions, gun.units) == (2, 2)
    assert (gun.best_price, gun.worst_price, gun.average_price) == (
        Decimal("50.00"),
        Decimal("50.00"),
        Decimal("50.00"),
    )
    assert gun.total_cost == Decimal("100.00")
    assert gun.gross_proceeds == Decimal("229.00")
    assert gun.net_proceeds == Decimal("229.00")
    assert gun.profit == Decimal("129.00")
    assert gun.margin_percent == Decimal("129.00")
    assert gun.output_slippage_percent == Decimal("13.26")
    assert gun.limit_reason == "marginal portion not profitable"
    assert gun.input_volume_m3 == pytest.approx(10.0)
    assert gun.market_path_names == ("Ship Equipment", "Weapons")
    assert [(m.type_id, m.name, m.quantity) for m in gun.materials] == [
        (34, "Tritanium", 110),
        (35, "Pyerite", 11),
    ]
    assert gun.flags == ()


def test_listing_walk_uses_fixed_five_percent_sell(static: Static) -> None:
    """Listing prices have no depth limit and no slippage."""
    gun = row(deals(static), 100, "list_sell_orders")
    # 110 * 1.10 + 11 * 2.20 = 145.20 per portion; profitable through 100 ISK.
    assert (gun.portions, gun.units) == (5, 5)
    assert gun.total_cost == Decimal("400.00")
    assert gun.gross_proceeds == Decimal("726.00")
    assert gun.profit == Decimal("326.00")
    assert gun.margin_percent == Decimal("81.50")
    assert gun.output_slippage_percent is None
    assert gun.limit_reason == "marginal portion not profitable"


def test_high_slippage_is_thin_and_unranked(static: Static) -> None:
    """Default slippage limit makes the immediate gun row thin."""
    gun = row(
        deals(static, options=replace(OPTIONS, max_slippage=Decimal(10))),
        100,
        "sell_to_buy_orders",
    )
    assert gun.status == "thin"
    assert gun.rank is None
    assert gun.flags == ("high_output_slippage",)


def test_supply_limit_small_profit_and_incomplete(static: Static) -> None:
    """Keep unranked profitable and incomplete rows; drop unlisted or zero rows."""
    report = deals(static)
    ammo = row(report, 101, "sell_to_buy_orders")
    assert (ammo.portions, ammo.units) == (1, 100)
    assert ammo.limit_reason == "input supply exhausted"
    assert ammo.profit == Decimal("4.00")
    assert ammo.status == "profitable" and ammo.rank is None
    for scenario, missing in (
        ("sell_to_buy_orders", "Unmarketable Salvage buy orders"),
        ("list_sell_orders", "Unmarketable Salvage 5% sell"),
    ):
        salvaged = row(report, 105, scenario)
        assert salvaged.status == "incomplete"
        assert salvaged.missing_data == (missing,)
        assert salvaged.best_price == Decimal("10.00")
        assert salvaged.portions == 0
        assert salvaged.total_cost is None and salvaged.profit is None
    assert {item.type_id for item in report.records} == {100, 101, 105}


def test_material_buy_depth_limit(static: Static) -> None:
    """Stop when a material buy book cannot absorb the next portion."""
    rows = [item for item in ORDERS if item[0] != 34 or not item[1]]
    rows.append((34, True, "1.00", 200, True))
    gun = row(
        deals(static, data=orders(rows=rows)),
        100,
        "sell_to_buy_orders",
    )
    assert gun.portions == 1
    assert gun.limit_reason == "Tritanium buy depth exhausted"


def test_fees_are_reported_and_quantized(static: Static) -> None:
    """Fees are percentages of gross; listing cost only applies to listings."""
    options = replace(
        OPTIONS,
        reprocessing_tax=Decimal(10),
        sales_tax=Decimal(5),
        broker_fee=Decimal(2),
    )
    report = deals(static, options=options)
    listed = row(report, 101, "list_sell_orders")
    assert listed.gross_proceeds == Decimal("5.50")
    assert listed.reprocessing_tax == Decimal("0.55")
    assert listed.sales_tax == Decimal("0.28")
    assert listed.listing_cost == Decimal("0.11")
    assert listed.net_proceeds == Decimal("4.56")
    assert listed.profit == Decimal("3.56")
    immediate = row(report, 101, "sell_to_buy_orders")
    assert immediate.listing_cost == Decimal("0.00")
    assert immediate.reprocessing_tax == Decimal("0.50")
    assert immediate.net_proceeds == Decimal("4.25")


def test_min_margin_stops_the_walk(static: Static) -> None:
    """A portion below the minimum margin is not bought."""
    gun = row(
        deals(static, options=replace(OPTIONS, min_margin=Decimal(100))),
        100,
        "sell_to_buy_orders",
    )
    assert gun.portions == 1


def test_history_flags_and_report_range(static: Static) -> None:
    """History is context: stale, far-below, missing, and liquidity flags."""
    records = {
        100: history(100, average="80.00", newest="2026-10-10"),
        34: history(34, volume="100"),
    }
    report = deals(static, history_records=records)
    gun = row(report, 100, "sell_to_buy_orders")
    assert gun.input_history_average == Decimal("80.00")
    assert gun.input_price_vs_history_percent == Decimal("-37.50")
    assert gun.input_history_daily_volume == Decimal("1")
    assert gun.input_history_missing_days == 1
    assert gun.input_history_newest_date == "2026-10-10"
    assert gun.worst_material_name == "Tritanium"
    assert gun.worst_material_days_of_volume == Decimal("2.20")
    assert gun.flags == (
        "input_far_below_history_avg",
        "history_stale",
        "exceeds_daily_volume",
    )
    assert gun.status == "thin" and gun.rank is None
    ammo = row(report, 101, "sell_to_buy_orders")
    assert "input_history_missing" in ammo.flags
    assert report.history_oldest_date == "2026-10-01"
    assert report.history_newest_date == "2026-10-10"
    assert deals(static).history_newest_date is None


def test_zero_volume_history_price_is_not_used(static: Static) -> None:
    """A zero history average means no traded volume, not a zero price."""
    report = deals(static, history_records={100: history(100, average="0", volume="0")})
    gun = row(report, 100, "sell_to_buy_orders")
    assert gun.input_history_average is None
    assert gun.input_price_vs_history_percent is None


def test_report_metadata_and_order(static: Static) -> None:
    """Rows group by scenario, ranked first by margin; staleness uses expiry."""
    report = deals(static)
    assert report.schema_version == 1
    assert report.system_name == "Jita" and report.region_id == JITA.region_id
    assert report.received_at == RECEIVED
    assert report.generated_at == GENERATED.format_iso()
    assert report.is_stale is True
    assert [(item.scenario, item.type_id) for item in report.records] == [
        ("sell_to_buy_orders", 100),
        ("sell_to_buy_orders", 101),
        ("sell_to_buy_orders", 105),
        ("list_sell_orders", 100),
        ("list_sell_orders", 101),
        ("list_sell_orders", 105),
    ]
    fresh = replace(orders(), expires_at=None, argus_expires_at="2026-10-19T00:00:00Z")
    assert deals(static, data=fresh).is_stale is False
    unknown = replace(orders(), expires_at=None)
    assert deals(static, data=unknown).is_stale is None


def test_mismatched_inputs_rejected(static: Static) -> None:
    """Reject datasets for another region or a different response."""
    data = orders()
    with pytest.raises(ValueError):
        collect_scrapmetal_deals(
            hub=AMARR,
            response=response(data),
            orders=data,
            summaries=calculate_dataset_summaries(data, system_id=JITA.system_id),
            types=static.types,
            type_materials=static.type_materials,
            market_groups=static.market_groups,
            history=None,
            options=OPTIONS,
            generated_at=GENERATED,
        )
    with pytest.raises(ValueError):
        collect_scrapmetal_deals(
            hub=JITA,
            response=replace(response(data), response_metadata_id=99),
            orders=data,
            summaries=calculate_dataset_summaries(data, system_id=JITA.system_id),
            types=static.types,
            type_materials=static.type_materials,
            market_groups=static.market_groups,
            history=None,
            options=OPTIONS,
            generated_at=GENERATED,
        )


def test_deals_renderers(static: Static) -> None:
    """CSV/JSON keep every row; Markdown ranks per scenario and explains limits."""
    report = deals(static)
    parsed = json.loads(render_scrapmetal_deals_json(report))
    assert parsed["schema_version"] == 1
    assert parsed["options"]["min_profit"] == "100"
    assert parsed["records"][0]["profit"] == "129.00"
    assert parsed["records"][2]["profit"] is None
    rendered = render_scrapmetal_deals_csv(report)
    assert "\r" not in rendered
    rows = list(csv.DictReader(StringIO(rendered)))
    assert len(rows) == 6
    assert rows[0]["system_name"] == "Jita"
    assert rows[0]["market_path_names"] == "Ship Equipment/Weapons"
    assert rows[0]["materials"] == "Tritanium x110;Pyerite x11"
    assert rows[0]["output_slippage_percent"] == "13.26"
    assert rows[2]["profit"] == "" and rows[2]["status"] == "incomplete"
    markdown = render_scrapmetal_deals_markdown(report)
    assert markdown.startswith("# Scrapmetal Reprocessing Deals: Jita\n")
    assert "Sell materials to buy orders (immediate)" in markdown
    assert "Post material sell orders at 5% sell price" in markdown
    assert "Scrap \\| Gun" in markdown
    assert "STALE" in markdown
    assert "`Limited by` definitions" in markdown
    assert "Listing cost" in markdown
    assert len(re.findall(r"^\|\s+1 \|", markdown, flags=re.MULTILINE)) == 2


def test_markdown_without_ranked_rows(static: Static) -> None:
    """Empty ranked tables say so instead of rendering nothing."""
    report = deals(static, options=replace(OPTIONS, min_profit=Decimal(10**9)))
    markdown = render_scrapmetal_deals_markdown(report)
    assert markdown.count("No opportunities meet the thresholds") == 2


def price_inputs(
    hub: MarketHub, data: models.MarketOrdersDataset, records: dict
) -> HubPriceInputs:
    """Bundle one hub's snapshot, summaries, and history lookup."""
    return HubPriceInputs(
        hub=hub,
        response=response(data),
        summaries=calculate_dataset_summaries(data, system_id=hub.system_id),
        history=records.get,
    )


def test_price_points(static: Static) -> None:
    """Per-unit break-even values per hub; missing material prices stay empty."""
    jita = orders()
    amarr = orders(AMARR, rows=[(34, True, "2.00", 10, True)])
    summaries = calculate_dataset_summaries(jita, system_id=JITA.system_id)
    trit_buy = summaries.records[34].buy_5
    assert trit_buy is not None
    report = collect_scrapmetal_price_points(
        hubs=(
            price_inputs(JITA, jita, {34: history(34, average="1.50")}),
            price_inputs(AMARR, amarr, {}),
        ),
        types=static.types,
        type_materials=static.type_materials,
        market_groups=static.market_groups,
        yield_percent=Decimal(55),
        generated_at=GENERATED,
    )
    assert report.schema_version == 1
    assert [hub.system_name for hub in report.hubs] == ["Jita", "Amarr"]
    assert report.hubs[0].orders_received_at == RECEIVED
    assert report.hubs[0].history_newest_date == "2026-10-17"
    assert report.hubs[1].history_newest_date is None
    assert [item.type_id for item in report.records] == [101, 105, 100, 106]
    ammo = report.records[0]
    assert ammo.type_name == "Ammo Pack" and ammo.portion_size == 100
    jita_ammo, amarr_ammo = ammo.values
    assert jita_ammo.buy == (trit_buy * 5 / 100).quantize(Decimal("0.01"))
    assert jita_ammo.sell == Decimal("0.06")
    assert jita_ammo.history == Decimal("0.08")
    assert amarr_ammo.buy == Decimal("0.10")
    assert amarr_ammo.sell is None and amarr_ammo.history is None
    assert (ammo.best_buy_hub, ammo.best_buy_value) == ("Amarr", Decimal("0.10"))
    gun = report.records[2]
    assert gun.values[0].sell == Decimal("145.20")
    assert gun.values[0].history is None
    assert gun.values[1].buy is None
    assert gun.unit_volume_m3 == pytest.approx(5.0)
    salvaged = report.records[1]
    assert salvaged.values[0].buy is None and salvaged.best_buy_hub is None
    tiny = report.records[3]
    assert tiny.values[0].buy == Decimal("0.00")


def test_price_point_renderers(static: Static) -> None:
    """Wide CSV with per-hub values and source metadata; JSON keeps nesting."""
    jita = orders()
    report = collect_scrapmetal_price_points(
        hubs=(price_inputs(JITA, jita, {}),),
        types=static.types,
        type_materials=static.type_materials,
        market_groups=static.market_groups,
        yield_percent=Decimal(55),
        generated_at=GENERATED,
    )
    rows = list(csv.DictReader(StringIO(render_scrapmetal_price_points_csv(report))))
    assert list(rows[0]) == [
        "generated_at",
        "yield_percent",
        "type_id",
        "type_name",
        "market_path_names",
        "portion_size",
        "unit_volume_m3",
        "jita_buy",
        "jita_sell",
        "jita_hist",
        "best_buy_hub",
        "best_buy_value",
        "jita_orders_received_at",
        "jita_history_newest_date",
    ]
    gun = rows[2]
    assert gun["jita_sell"] == "145.20" and gun["jita_hist"] == ""
    assert gun["jita_orders_received_at"] == RECEIVED
    assert gun["market_path_names"] == "Ship Equipment/Weapons"
    parsed = json.loads(render_scrapmetal_price_points_json(report))
    assert parsed["hubs"][0]["system_name"] == "Jita"
    assert parsed["records"][2]["values"][0]["sell"] == "145.20"


@dataclass(slots=True, kw_only=True)
class Environment:
    """On-disk local inputs exercised through the registered root CLI."""

    settings: EveArgusSettings
    dynamic_path: Path
    history_path: Path


@pytest.fixture
def environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Environment:
    """Set up real databases and forbid network resource initialization."""
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
                        hub.station_id,
                        hub.region_id * 100 + order_id,
                        int(Decimal(price) * 100),
                        hub.system_id if in_hub else hub.system_id + 1,
                        type_id,
                        volume,
                        volume,
                    )
                    for order_id, (type_id, is_buy, price, volume, in_hub) in enumerate(
                        ORDERS, 1
                    )
                ],
            )
        connection.commit()


def save_history(env: Environment, *, hub: MarketHub = JITA) -> None:
    """Store nine days of history for the gun and Tritanium in one region."""
    with closing(sqlite3.connect(env.history_path)) as connection:
        connection.executescript(history_util.load_table_definitions())
        connection.executemany(
            """INSERT INTO market_history
            (received_at, expires_at, region_id, type_id, average, date_, highest,
             lowest, order_count, volume)
            VALUES ('2026-10-18T12:00:00Z', NULL, ?, ?, ?, ?, ?, ?, 3, ?)""",
            [
                (
                    hub.region_id,
                    type_id,
                    cents,
                    f"2026-10-{day:02d}",
                    cents,
                    cents,
                    volume,
                )
                for type_id, cents, volume in ((100, 6000, 1), (34, 100, 1000))
                for day in range(9, 18)
            ],
        )
        connection.commit()


def invoke(env: Environment, destination: Path, *args: str) -> Result:
    """Run actual registration, readers, collectors, and renderers."""
    return CliRunner().invoke(
        app,
        ["reports", "scrapmetal", "--to", str(destination), *args],
        obj={SETTINGS_KEY: env.settings},
    )


def test_cli_registered_with_options() -> None:
    """The command is registered under reports and exposes calculation options."""
    runner = CliRunner()
    assert "scrapmetal" in runner.invoke(app, ["reports", "--help"]).output
    result = runner.invoke(app, ["reports", "scrapmetal", "--help"])
    assert result.exit_code == 0
    for option in (
        "--to",
        "--overwrite",
        "--quiet",
        "--yield-percent",
        "--reprocessing-tax",
        "--sales-tax",
        "--broker-fee",
        "--min-profit",
        "--min-margin",
        "--max-slippage",
    ):
        assert option in result.output


def test_cli_writes_all_outputs_without_history(
    environment: Environment, tmp_path: Path
) -> None:
    """Missing history warns and continues; options reach every output."""
    save_orders(environment)
    destination = tmp_path / "reports"
    result = invoke(
        environment, destination, "--quiet", "--sales-tax", "5", "--min-profit", "100"
    )
    assert result.exit_code == 0, result.output
    assert "Wrote" not in result.output
    assert "market history database not found" in result.output
    assert "eve-argus fetch market-history --hubs --scrapmetal" in result.output
    assert "order snapshot has expired" in result.output
    names = sorted(path.name for path in destination.iterdir())
    assert len(names) == 17
    stamp = file_safe_string(RECEIVED)
    for hub in MARKET_HUBS:
        for suffix in ("md", "csv", "json"):
            assert f"scrapmetal-deals-{hub.system_name}-{stamp}.{suffix}" in names
    assert sum(name.startswith("scrapmetal-price-points-") for name in names) == 2
    parsed = json.loads(
        (destination / f"scrapmetal-deals-Jita-{stamp}.json").read_text()
    )
    assert parsed["options"]["sales_tax"] == "5"
    assert parsed["history_newest_date"] is None
    gun = next(
        item
        for item in parsed["records"]
        if item["type_id"] == 100 and item["scenario"] == "sell_to_buy_orders"
    )
    assert gun["sales_tax"] == "11.45" and gun["status"] == "thin"
    points = next(destination.glob("scrapmetal-price-points-*.csv")).read_text()
    header = points.splitlines()[0].split(",")
    assert "rens_hist" in header and "amarr_orders_received_at" in header


def test_cli_uses_history_when_available(
    environment: Environment, tmp_path: Path
) -> None:
    """History adds context to deals and price points for hubs that have it."""
    save_orders(environment)
    save_history(environment)
    destination = tmp_path / "reports"
    result = invoke(environment, destination)
    assert result.exit_code == 0, result.output
    assert "Wrote" in result.output
    assert "No market history for Amarr" in result.output
    assert "No market history for Jita" not in result.output
    stamp = file_safe_string(RECEIVED)
    parsed = json.loads(
        (destination / f"scrapmetal-deals-Jita-{stamp}.json").read_text()
    )
    assert parsed["history_newest_date"] == "2026-10-18"
    gun = next(item for item in parsed["records"] if item["type_id"] == 100)
    assert gun["input_history_average"] == "60.00"
    points = json.loads(
        next(destination.glob("scrapmetal-price-points-*.json")).read_text()
    )
    assert points["hubs"][0]["history_newest_date"] == "2026-10-18"
    assert points["hubs"][1]["history_newest_date"] is None


def test_cli_missing_orders_writes_nothing(
    environment: Environment, tmp_path: Path
) -> None:
    """Every hub snapshot is required before anything is written."""
    save_orders(environment, hubs=[JITA])
    destination = tmp_path / "reports"
    result = invoke(environment, destination)
    assert result.exit_code == 1
    assert "Amarr" in result.output
    assert "eve-argus fetch market-orders --hubs" in result.output
    assert not destination.exists()


def test_cli_existing_outputs_require_overwrite(
    environment: Environment, tmp_path: Path
) -> None:
    """Existing deal files are preserved unless --overwrite is passed."""
    save_orders(environment)
    destination = tmp_path / "reports"
    assert invoke(environment, destination, "--quiet").exit_code == 0
    path = destination / f"scrapmetal-deals-Jita-{file_safe_string(RECEIVED)}.csv"
    path.write_text("keep")
    result = invoke(environment, destination, "--quiet")
    assert result.exit_code == 1 and "--overwrite" in result.output
    assert path.read_text() == "keep"
    result = invoke(environment, destination, "--quiet", "--overwrite")
    assert result.exit_code == 0, result.output
    assert path.read_text() != "keep"


@pytest.mark.parametrize(
    "args",
    [
        ("--yield-percent", "101"),
        ("--sales-tax", "-1"),
        ("--min-profit", "-5"),
    ],
)
def test_cli_rejects_out_of_range_options(
    environment: Environment, tmp_path: Path, args: tuple[str, str]
) -> None:
    """Typer rejects invalid ranges before any database is read."""
    result = invoke(environment, tmp_path / "reports", *args)
    assert result.exit_code == 2
    assert not (tmp_path / "reports").exists()
