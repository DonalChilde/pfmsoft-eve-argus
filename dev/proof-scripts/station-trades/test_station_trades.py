"""Synthetic acceptance tests for the station-trades proof."""

import csv
import sqlite3
import sys
from contextlib import closing
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from pfmsoft.eve_argus.static import models as static_models

sys.path.insert(0, str(Path(__file__).resolve().parent))
import station_trades as proof


def test_unit_economics_matches_prompt_example() -> None:
    """Keep fee arithmetic exact for the report's worked example."""
    result = proof.calculate_unit_economics(
        buy_price=Decimal("100"),
        sell_price=Decimal("120"),
        acquisition_broker_fee_percent=Decimal("1"),
        sale_broker_fee_percent=Decimal("1"),
        sales_tax_percent=Decimal("2"),
        regional_daily_volume=Decimal("200"),
        participation_percent=Decimal("1"),
    )

    assert result.acquisition_broker_fee_per_unit == Decimal("1")
    assert result.sale_broker_fee_per_unit == Decimal("1.2")
    assert result.sales_tax_per_unit == Decimal("2.4")
    assert result.acquisition_cost_per_unit == Decimal("101")
    assert result.net_sale_proceeds_per_unit == Decimal("116.4")
    assert result.net_profit_per_unit == Decimal("15.4")
    assert result.net_margin_percent == Decimal("15.4") / Decimal("101") * 100
    assert result.estimated_daily_units == Decimal("2")
    assert result.estimated_daily_net_profit == Decimal("30.8")
    assert result.modeled_acquisition_capital == Decimal("202")
    assert result.modeled_sale_listing_cost == Decimal("2.4")


def test_unit_economics_preserves_fractional_throughput() -> None:
    """Rank math keeps fractional average daily units; order units are floored."""
    result = proof.calculate_unit_economics(
        buy_price=Decimal("100"),
        sell_price=Decimal("120"),
        acquisition_broker_fee_percent=Decimal("1"),
        sale_broker_fee_percent=Decimal("1"),
        sales_tax_percent=Decimal("2"),
        regional_daily_volume=Decimal("150"),
        participation_percent=Decimal("1"),
    )

    assert result.estimated_daily_units == Decimal("1.5")
    assert result.estimated_daily_net_profit == Decimal("23.10")
    assert result.one_day_order_units == 1
    assert result.one_day_order_acquisition_capital == Decimal("101")


@pytest.mark.parametrize(
    ("best_buy", "best_sell", "expected_buy", "expected_sell", "invalid"),
    [
        ("100.00", "120.00", "100.1", "119.9", False),
        ("0.01", "0.02", "0.02", "0.01", True),
        ("100.00", "0.01", "100.1", None, True),
        ("999900", "1000000", "1000000", "999900", True),
        ("1112000", "1112000", "1113000", "1111000", True),
    ],
)
def test_significant_figure_price_targets(
    best_buy: str,
    best_sell: str,
    expected_buy: str,
    expected_sell: str | None,
    invalid: bool,
) -> None:
    """Apply the four-significant-figure grid across price-band boundaries."""
    buy, sell, is_invalid = proof.proposed_price_targets(
        best_buy=Decimal(best_buy),
        best_sell=Decimal(best_sell),
    )

    assert buy == Decimal(expected_buy)
    assert sell == (Decimal(expected_sell) if expected_sell is not None else None)
    assert is_invalid is invalid


@pytest.mark.parametrize(
    ("price", "expected_tick"),
    [
        ("0.01", "0.01"),
        ("0.99", "0.01"),
        ("1", "0.01"),
        ("999900", "100"),
        ("1000000", "1000"),
        ("1112000", "1000"),
    ],
)
def test_market_tick_size_uses_four_significant_figures(
    price: str, expected_tick: str
) -> None:
    """Use four significant digits, bounded by the minimum price step."""
    assert proof.market_tick(Decimal(price)) == Decimal(expected_tick)


def test_evaluate_opportunity_uses_status_precedence_and_daily_history() -> None:
    """Missing sides/history and zero volume do not become positive ranks."""
    missing_buy = proof.evaluate_opportunity(
        best_buy=None,
        best_sell=Decimal("10"),
        regional_daily_volume=Decimal("10"),
    )
    crossing = proof.evaluate_opportunity(
        best_buy=Decimal("10"),
        best_sell=Decimal("10.01"),
        regional_daily_volume=Decimal("10"),
    )
    missing_history = proof.evaluate_opportunity(
        best_buy=Decimal("10"),
        best_sell=Decimal("11"),
        regional_daily_volume=None,
    )
    zero_volume = proof.evaluate_opportunity(
        best_buy=Decimal("10"),
        best_sell=Decimal("11"),
        regional_daily_volume=Decimal("0"),
    )
    ranked = proof.evaluate_opportunity(
        best_buy=Decimal("100"),
        best_sell=Decimal("120"),
        regional_daily_volume=Decimal("200"),
    )

    assert missing_buy[0] == "missing_buy"
    assert crossing[0] == "invalid_price_target"
    assert missing_history[0] == "missing_history"
    assert missing_history[3] is not None
    assert missing_history[3].estimated_daily_units is None
    assert zero_volume[0] == "zero_history_volume"
    assert zero_volume[3].estimated_daily_units == 0
    assert ranked[0] == "ranked"
    assert ranked[1] == Decimal("100.1")
    assert ranked[2] == Decimal("119.9")
    assert ranked[3].estimated_daily_net_profit == Decimal("39.6")


def test_ranking_prefers_daily_profit_before_margin() -> None:
    """A lower-margin opportunity can rank first on higher daily net profit."""
    template = _sample_report().records[0]
    high_daily = proof.replace(
        template,
        status="ranked",
        economics=proof.UnitEconomics(
            acquisition_broker_fee_per_unit=Decimal(0),
            sale_broker_fee_per_unit=Decimal(0),
            sales_tax_per_unit=Decimal(0),
            acquisition_cost_per_unit=Decimal(100),
            net_sale_proceeds_per_unit=Decimal(110),
            net_profit_per_unit=Decimal(10),
            net_margin_percent=Decimal(10),
            estimated_daily_units=Decimal(100),
            estimated_daily_net_profit=Decimal(1000),
            daily_acquisition_broker_fee=Decimal(0),
            daily_sale_broker_fee=Decimal(0),
            daily_sales_tax=Decimal(0),
            modeled_acquisition_capital=Decimal(10000),
            modeled_sale_listing_cost=Decimal(0),
            one_day_order_units=100,
            one_day_order_acquisition_capital=Decimal(10000),
        ),
    )
    high_margin = proof.replace(
        high_daily,
        type_id=35,
        type_name="Another item",
        economics=proof.replace(
            high_daily.economics,
            net_margin_percent=Decimal(20),
            estimated_daily_net_profit=Decimal(500),
        ),
    )

    assert sorted((high_margin, high_daily), key=proof._rank_key) == [
        high_daily,
        high_margin,
    ]


def test_positive_spread_erased_by_fees_is_unprofitable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fee costs participate in ranking eligibility, not just displayed totals."""
    monkeypatch.setattr(proof, "SALES_TAX_PERCENT", Decimal("1"))
    status, _, _, economics = proof.evaluate_opportunity(
        best_buy=Decimal("100"),
        best_sell=Decimal("101.02"),
        regional_daily_volume=Decimal("100"),
    )

    assert status == "unprofitable"
    assert economics is not None
    assert economics.net_profit_per_unit == Decimal("-0.11")


@pytest.mark.parametrize(
    ("fee", "participation"),
    [
        (Decimal("-0.01"), Decimal("1")),
        (Decimal("100.01"), Decimal("1")),
        (Decimal("0"), Decimal("0")),
        (Decimal("0"), Decimal("100.01")),
        (Decimal("NaN"), Decimal("1")),
    ],
)
def test_unit_economics_rejects_invalid_percentages(
    fee: Decimal, participation: Decimal
) -> None:
    """Reject invalid configuration instead of producing successful-looking output."""
    with pytest.raises(ValueError):
        proof.calculate_unit_economics(
            buy_price=Decimal("100"),
            sell_price=Decimal("120"),
            acquisition_broker_fee_percent=fee,
            sale_broker_fee_percent=Decimal(0),
            sales_tax_percent=Decimal(0),
            regional_daily_volume=Decimal("200"),
            participation_percent=participation,
        )


def test_history_window_uses_one_shared_ten_day_calendar_window() -> None:
    """History windows end on the newest stored date before the current UTC date."""
    window = proof.select_history_window(
        newest_stored_date="2026-10-25",
        generation_date=date(2026, 10, 26),
    )

    assert window.newest_date == "2026-10-25"
    assert window.oldest_date == "2026-10-16"
    assert window.dates[0] == "2026-10-25"
    assert window.dates[-1] == "2026-10-16"
    assert len(window.dates) == 10


def test_history_window_rejects_dates_not_before_generation_date() -> None:
    """Today's and future history dates must not leak into the report window."""
    with pytest.raises(ValueError, match="strictly before"):
        proof.select_history_window(
            newest_stored_date="2026-10-26",
            generation_date=date(2026, 10, 26),
        )


def test_history_metrics_uses_full_ten_day_denominator_and_reports_missing_days() -> (
    None
):
    """Eight dates with 1,000 units average 100 units over the ten-day window."""
    hub = proof.MARKET_HUBS[0]
    window = proof.select_history_window(
        newest_stored_date="2026-10-25",
        generation_date=date(2026, 10, 26),
    )
    records = tuple(
        proof.history_models.MarketHistoryRecord(
            received_at="2026-10-26T10:00:00Z",
            expires_at=None,
            argus_expires_at=None,
            region_id=hub.region_id,
            type_id=34,
            average=Decimal("10"),
            date=day,
            highest=Decimal("12"),
            lowest=Decimal("8"),
            order_count=10,
            volume=125,
        )
        for day in window.dates[:8]
    )

    metrics = proof.calculate_history_metrics(
        records=records,
        hub=hub,
        type_id=34,
        window=window,
        generation_date=date(2026, 10, 26),
    )

    assert metrics.average_daily_volume == Decimal("100")
    assert metrics.average_price == Decimal("10")
    assert metrics.missing_days == 2
    assert metrics.newest_date_used == window.newest_date
    assert metrics.oldest_date_used == window.dates[7]


def test_csv_header_has_stable_column_order() -> None:
    """Keep the declared columns in a stable order."""
    headers = proof.STATION_CSV_FIELDS
    assert headers[:5] == (
        "generated_at",
        "order_response_metadata_id",
        "orders_received_at",
        "orders_expires_at",
        "orders_argus_expires_at",
    )
    assert headers.index("type_id") < headers.index("status")
    assert headers.index("proposed_buy_price") < headers.index("net_profit_per_unit")
    assert headers[-1] == "one_day_order_acquisition_capital"


def _sample_report() -> proof.StationTradeReport:
    hub = proof.MARKET_HUBS[0]
    return proof.StationTradeReport(
        hub=hub,
        generated_at="2026-10-26T12:00:00Z",
        order_response_metadata_id=12,
        orders_received_at="2026-10-26T10:00:00Z",
        orders_expires_at=None,
        orders_argus_expires_at=None,
        orders_expiry_used=None,
        orders_freshness="unknown",
        history_window=None,
        warnings=("The fixed tick is provisional.",),
        records=(
            proof.StationCandidate(
                type_id=34,
                type_name='Tritanium, "refined"',
                market_group_id=1857,
                market_path="Materials/Minerals",
                status="missing_history",
                rank=None,
                flags=("unknown_order_expiry",),
                missing_data=("regional_history",),
                best_station_buy_price=Decimal("100"),
                best_station_sell_price=Decimal("120"),
                proposed_buy_price=Decimal("100.1"),
                proposed_sell_price=Decimal("119.9"),
                five_percent_buy=None,
                five_percent_sell=None,
                station_buy_remaining_quantity=10,
                station_sell_remaining_quantity=20,
                station_buy_order_count=1,
                station_sell_order_count=1,
                station_buy_order_context=(
                    proof.OrderContext(
                        order_id=7,
                        price=Decimal("100"),
                        volume_remain=10,
                        range="station",
                        min_volume=1,
                    ),
                ),
                station_sell_order_context=(
                    proof.OrderContext(
                        order_id=8,
                        price=Decimal("120"),
                        volume_remain=20,
                        range="station",
                        min_volume=2,
                    ),
                ),
                history=proof.HistoryMetrics(
                    received_at=None,
                    expires_at=None,
                    argus_expires_at=None,
                    freshness="missing",
                    oldest_date_used=None,
                    newest_date_used=None,
                    missing_days=None,
                    average_price=None,
                    average_daily_volume=None,
                    average_daily_order_count=None,
                ),
                economics=proof.UnitEconomics(
                    acquisition_broker_fee_per_unit=Decimal("0"),
                    sale_broker_fee_per_unit=Decimal("0"),
                    sales_tax_per_unit=Decimal("0"),
                    acquisition_cost_per_unit=Decimal("100.1"),
                    net_sale_proceeds_per_unit=Decimal("119.9"),
                    net_profit_per_unit=Decimal("19.8"),
                    net_margin_percent=Decimal("19.8") / Decimal("100.1") * 100,
                    estimated_daily_units=None,
                    estimated_daily_net_profit=None,
                    daily_acquisition_broker_fee=None,
                    daily_sale_broker_fee=None,
                    daily_sales_tax=None,
                    modeled_acquisition_capital=None,
                    modeled_sale_listing_cost=None,
                    one_day_order_units=None,
                    one_day_order_acquisition_capital=None,
                ),
            ),
        ),
    )


def test_csv_and_json_keep_unknown_daily_metrics_null() -> None:
    """Known prices get per-unit economics while missing history stays unknown."""
    report = _sample_report()

    row = next(csv.DictReader(proof.render_station_csv(report).splitlines()))
    assert row["type_name"] == 'Tritanium, "refined"'
    assert row["proposed_buy_price"] == "100.1"
    assert row["proposed_sell_price"] == "119.9"
    assert row["net_profit_per_unit"] == "19.8"
    assert row["estimated_daily_net_profit"] == ""
    assert row["station_id"] == str(report.hub.station_id)
    assert '"min_volume":1' in row["station_buy_order_context"]
    assert '"range":"station"' in row["station_sell_order_context"]

    record = proof.report_payload(report)["records"][0]
    assert record["proposed_buy_price"] == "100.1"
    assert record["history"]["average_daily_volume"] is None
    assert record["economics"]["estimated_daily_units"] is None
    assert proof.report_payload(report)["summary"]["ranked_count"] == 0


def test_write_reports_preflights_collisions_and_honors_overwrite(
    tmp_path: Path,
) -> None:
    """Write all formats only after preflight, preserving exclusive-create default."""
    destination = tmp_path / "reports"
    first_write = proof.write_reports(
        (_sample_report(),),
        destination=destination,
        overwrite=False,
    )
    assert len(first_write) == 3
    before = {path: path.read_text(encoding="utf-8") for path in first_write}

    with pytest.raises(FileExistsError, match="--overwrite"):
        proof.write_reports(
            (_sample_report(),),
            destination=destination,
            overwrite=False,
        )
    assert {path: path.read_text(encoding="utf-8") for path in first_write} == before

    overwritten = proof.write_reports(
        (_sample_report(),),
        destination=destination,
        overwrite=True,
    )
    assert overwritten == first_write


def test_database_opens_read_only(tmp_path: Path) -> None:
    """The proof's database helper cannot mutate its input."""
    path = tmp_path / "source.sqlite"
    with sqlite3.connect(path) as database:
        database.execute("CREATE TABLE marker (value INTEGER)")

    with closing(proof.open_database(path)) as database:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            database.execute("INSERT INTO marker VALUES (1)")


def test_markdown_is_formatted_and_idempotent() -> None:
    """Markdown uses the shared formatter and repeat rendering is stable."""
    report = _sample_report()
    rendered = proof.render_station_markdown(report)

    assert "four significant" in rendered
    assert "No opportunities meet the ranking criteria" in rendered
    table_lines = [line for line in rendered.splitlines() if line.startswith("|")]
    widths = {len(line.split("|")) for line in table_lines}
    assert 21 in widths
    assert 10 in widths
    assert proof.render_station_markdown(report) == rendered


def test_markdown_ranked_table_includes_history_and_station_context() -> None:
    """Ranked rows surface order depth, history coverage, and price deviations."""
    report = _sample_report()
    candidate = report.records[0]
    ranked_candidate = replace(
        candidate,
        status="ranked",
        rank=1,
        five_percent_buy=proof.SideSummary(
            five_price=Decimal("100"),
            five_orders=2,
            five_items=30,
            total_items=40,
            total_orders=3,
            filtered_items=0,
            filtered_orders=0,
        ),
        five_percent_sell=proof.SideSummary(
            five_price=Decimal("120"),
            five_orders=4,
            five_items=50,
            total_items=60,
            total_orders=5,
            filtered_items=0,
            filtered_orders=0,
        ),
        history=replace(
            candidate.history,
            oldest_date_used="2026-10-15",
            newest_date_used="2026-10-25",
            missing_days=2,
            average_price=Decimal("110"),
        ),
    )
    rendered = proof.render_station_markdown(
        replace(report, records=(ranked_candidate,))
    )

    assert "5% buy 2/30, sell 4/50" in rendered
    assert "2026-10-15 to 2026-10-25; 2 missing" in rendered
    assert "-9.00%" in rendered
    assert "9.00%" in rendered


def _order(
    *,
    order_id: int,
    location_id: int,
    is_buy_order: bool,
    price: str,
    volume_remain: int,
) -> proof.dynamic_models.MarketOrderRecord:
    return proof.dynamic_models.MarketOrderRecord(
        response_metadata_id=1,
        region_id=10000002,
        duration=90,
        is_buy_order=is_buy_order,
        issued="2026-10-26T00:00:00Z",
        location_id=location_id,
        min_volume=1,
        order_id=order_id,
        price=Decimal(price),
        range="station",
        system_id=30000142,
        type_id=34,
        volume_remain=volume_remain,
        volume_total=max(1, volume_remain),
    )


def test_station_order_selection_excludes_other_stations_and_exhausted_orders() -> None:
    """Only positive-volume orders anchored at the exact primary station remain."""
    selected = proof.station_active_orders(
        (
            _order(
                order_id=1,
                location_id=60003760,
                is_buy_order=True,
                price="100",
                volume_remain=10,
            ),
            _order(
                order_id=2,
                location_id=60003761,
                is_buy_order=True,
                price="999",
                volume_remain=10,
            ),
            _order(
                order_id=3,
                location_id=60003760,
                is_buy_order=False,
                price="0",
                volume_remain=0,
            ),
        ),
        response_metadata_id=1,
        region_id=10000002,
        type_id=34,
        station_id=60003760,
    )

    assert [order.order_id for order in selected] == [1]


def test_collect_report_uses_station_scope_and_preserves_depth_summary() -> None:
    """Another station's orders cannot set best prices or station depth."""
    hub = proof.MARKET_HUBS[0]
    response = proof.dynamic_models.MarketOrdersResponse(
        response_metadata_id=1,
        received_at="2026-10-26T10:00:00Z",
        expires_at=None,
        argus_expires_at=None,
        region_id=hub.region_id,
    )
    buys = (
        _order(
            order_id=1,
            location_id=hub.station_id,
            is_buy_order=True,
            price="100",
            volume_remain=10,
        ),
        _order(
            order_id=2,
            location_id=hub.station_id + 1,
            is_buy_order=True,
            price="999",
            volume_remain=100,
        ),
    )
    sells = (
        _order(
            order_id=3,
            location_id=hub.station_id,
            is_buy_order=False,
            price="120",
            volume_remain=20,
        ),
        _order(
            order_id=4,
            location_id=hub.station_id,
            is_buy_order=False,
            price="1",
            volume_remain=0,
        ),
    )
    dataset = proof.dynamic_models.MarketOrdersDataset(
        response_metadata_id=response.response_metadata_id,
        received_at=response.received_at,
        expires_at=response.expires_at,
        argus_expires_at=response.argus_expires_at,
        region_id=hub.region_id,
        records={
            34: proof.dynamic_models.BuySellOrders(buy_orders=buys, sell_orders=sells)
        },
    )
    market_group = static_models.MarketGroupsRecord(
        market_group_id=516,
        description="",
        has_types=True,
        icon_id=None,
        int_path=(516,),
        name="Minerals",
        parent_group_id=None,
        str_path=("Minerals",),
        types=(34,),
    )
    report = proof._collect_report(
        hub=hub,
        response=response,
        order_dataset=dataset,
        types={
            34: proof.ProofTypeRecord(
                type_id=34,
                market_group_id=516,
                name="Tritanium",
                published=True,
            )
        },
        market_groups={516: market_group},
        history_connection=None,
        generated_at="2026-10-26T12:00:00Z",
        generation_date=date(2026, 10, 26),
        history_window=None,
    )

    record = report.records[0]
    assert record.best_station_buy_price == Decimal("100")
    assert record.best_station_sell_price == Decimal("120")
    assert record.station_buy_remaining_quantity == 10
    assert record.station_sell_remaining_quantity == 20
    assert record.station_buy_order_count == 1
    assert record.station_sell_order_count == 1
    assert record.station_buy_order_context[0].range == "station"
    assert record.station_buy_order_context[0].min_volume == 1
    assert record.five_percent_buy is not None
    assert record.five_percent_buy.five_items == 10
    assert record.five_percent_buy.five_orders == 1
    assert record.proposed_buy_price == Decimal("100.1")
    assert record.proposed_sell_price == Decimal("119.9")
    assert record.status == "missing_history"
    assert record.rank is None


def test_collect_report_accepts_an_empty_newest_snapshot() -> None:
    """An empty current snapshot produces an explicit, exportable empty report."""
    hub = proof.MARKET_HUBS[0]
    response = proof.dynamic_models.MarketOrdersResponse(
        response_metadata_id=2,
        received_at="2026-10-26T10:00:00Z",
        expires_at=None,
        argus_expires_at=None,
        region_id=hub.region_id,
    )
    dataset = proof.dynamic_models.MarketOrdersDataset(
        response_metadata_id=2,
        received_at=response.received_at,
        expires_at=None,
        argus_expires_at=None,
        region_id=hub.region_id,
        records={},
    )
    report = proof._collect_report(
        hub=hub,
        response=response,
        order_dataset=dataset,
        types={},
        market_groups={},
        history_connection=None,
        generated_at="2026-10-26T12:00:00Z",
        generation_date=date(2026, 10, 26),
        history_window=None,
    )

    assert report.records == ()
    assert len(proof.render_station_csv(report).splitlines()) == 1
    assert (
        "No opportunities meet the ranking criteria"
        in proof.render_station_markdown(report)
    )
    assert proof.report_payload(report)["records"] == []


def test_snapshot_selection_uses_newest_response_and_fails_missing_regions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Select the reader's newest response, even if it is the empty snapshot."""

    def responses(
        _connection: sqlite3.Connection, *, region_id: int
    ) -> list[proof.dynamic_models.MarketOrdersResponse]:
        return [
            proof.dynamic_models.MarketOrdersResponse(
                response_metadata_id=2,
                received_at="2026-10-26T10:00:00Z",
                expires_at=None,
                argus_expires_at=None,
                region_id=region_id,
            ),
            proof.dynamic_models.MarketOrdersResponse(
                response_metadata_id=1,
                received_at="2026-10-25T10:00:00Z",
                expires_at=None,
                argus_expires_at=None,
                region_id=region_id,
            ),
        ]

    monkeypatch.setattr(proof.dynamic_read, "market_orders_responses", responses)
    with closing(sqlite3.connect(":memory:")) as connection:
        selected = proof._latest_order_responses(connection)
    assert {response.response_metadata_id for response in selected.values()} == {2}

    monkeypatch.setattr(
        proof.dynamic_read,
        "market_orders_responses",
        lambda _connection, *, region_id: [],
    )
    with (
        closing(sqlite3.connect(":memory:")) as connection,
        pytest.raises(ValueError, match="fetch market-orders --hubs"),
    ):
        proof._latest_order_responses(connection)


@pytest.mark.parametrize(
    ("price", "volume_remain", "error"),
    [
        ("0", 1, "nonpositive price"),
        ("10", -1, "negative remaining volume"),
    ],
)
def test_station_order_selection_rejects_invalid_active_orders(
    price: str, volume_remain: int, error: str
) -> None:
    """Reject active station orders with invalid prices or remaining volumes."""
    with pytest.raises(ValueError, match=error):
        proof.station_active_orders(
            (
                _order(
                    order_id=99,
                    location_id=60003760,
                    is_buy_order=True,
                    price=price,
                    volume_remain=volume_remain,
                ),
            ),
            response_metadata_id=1,
            region_id=10000002,
            type_id=34,
            station_id=60003760,
        )
