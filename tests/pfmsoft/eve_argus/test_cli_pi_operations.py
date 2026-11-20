"""Verify standalone PI operations output from stored snapshot inputs."""

import json
import re
from contextlib import nullcontext
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from pfmsoft.eve_argus.cli import app
from pfmsoft.eve_argus.cli.reports import planetary_operations as command
from pfmsoft.eve_argus.dynamic.models import MarketOrderRecord, MarketOrdersResponse
from pfmsoft.eve_argus.pi.catalog import load_catalog
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings


def test_standalone_report_uses_latest_orders_and_keeps_scope_separate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run real collectors and rendering with independent synthetic scope prices."""
    catalog = load_catalog()
    settings = Mock(spec=EveArgusSettings)
    settings.argus_dynamic_database = tmp_path / "orders.db"
    settings.argus_dynamic_database.touch()
    settings.market_history_database = tmp_path / "missing.db"
    response = MarketOrdersResponse(
        response_metadata_id=7,
        received_at="2025-01-02T10:00:00Z",
        expires_at="2025-01-02T11:00:00Z",
        argus_expires_at=None,
        region_id=10000002,
    )
    other_response = Mock(response_metadata_id=6)
    orders = tuple(
        MarketOrderRecord(
            response_metadata_id=7,
            region_id=10000002,
            duration=90,
            is_buy_order=False,
            issued=response.received_at,
            location_id=location,
            min_volume=1,
            order_id=location,
            price=Decimal(price),
            range="station",
            system_id=system,
            type_id=2393,
            volume_remain=100,
            volume_total=100,
        )
        for system, location, price in (
            (30000142, 60003760, "105.25"),
            (30000142, 61000000, "100.25"),
            (30000144, 62000000, "95.25"),
        )
    )

    def filtered(
        _connection: object, response_id: int, *, type_id: int
    ) -> tuple[MarketOrderRecord, ...]:
        assert response_id == 7
        return orders if type_id == 2393 else ()

    connection = Mock(side_effect=lambda *args, **kwargs: nullcontext(object()))
    monkeypatch.setattr(command, "db_connection_manager", connection)
    monkeypatch.setattr(
        command, "get_static_database_path", lambda _: tmp_path / "sde.db"
    )
    monkeypatch.setattr(
        command.dynamic_read,
        "market_orders_responses",
        Mock(return_value=(response, other_response)),
    )
    monkeypatch.setattr(command.dynamic_read, "market_orders_filtered", filtered)
    monkeypatch.setattr(
        command.static_read,
        "types",
        Mock(
            return_value={
                type_id: SimpleNamespace(
                    type_id=type_id, name=material.name, market_group_id=None
                )
                for type_id, material in catalog.items()
            }
        ),
    )
    monkeypatch.setattr(command.static_read, "market_groups", Mock(return_value={}))

    output = tmp_path / "operations.html"
    original = tmp_path / "index.html"
    original.write_text("existing browser", encoding="utf-8")
    arguments = ["reports", "planetary-operations", "--to", str(output), "--quiet"]
    runner = CliRunner()
    context = {SETTINGS_KEY: settings}
    result = runner.invoke(app, arguments, obj=context)
    assert result.exit_code == 0, (result.output, result.exception)
    assert "stale" in result.output
    assert "No priced The Forge history" in result.output
    assert "Open" not in result.output
    assert original.read_text(encoding="utf-8") == "existing browser"
    assert not settings.market_history_database.exists()
    html = output.read_text(encoding="utf-8")
    assert not re.search(r"<(?:script|link)\b[^>]*(?:src|href)=", html)
    materials = json.loads(html.split("const piSnapshot = ", 1)[1].split(";\n", 1)[0])
    assert len(materials) == 83
    assert materials["2393"]["prices"] == {
        "Jita Buy 5%": None,
        "Jita Sell 5%": "100.25",
        "The Forge Avg": None,
    }
    data = json.loads(html.split("const marketReports = ", 1)[1].split(";\n", 1)[0])
    assert len(data["jita"]["records"]) == len(data["forge-history"]["records"]) == 83
    forge_row = next(
        row for row in data["forge-prices"]["records"] if row["type_id"] == 2393
    )
    assert forge_row["sell_summary"]["five_price"] == "95.25"
    assert all(call.kwargs == {"read_only": True} for call in connection.call_args_list)

    connection.reset_mock()
    assert runner.invoke(app, arguments, obj=context).exit_code == 1
    connection.assert_not_called()
    assert runner.invoke(app, [*arguments, "--overwrite"], obj=context).exit_code == 0


def test_missing_orders_does_not_create_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing required input produces an actionable error, not empty output."""
    settings = Mock(spec=EveArgusSettings)
    settings.argus_dynamic_database = tmp_path / "missing.db"
    connection = Mock()
    monkeypatch.setattr(command, "db_connection_manager", connection)
    output = tmp_path / "new" / "operations.html"
    result = CliRunner().invoke(
        app,
        ["reports", "planetary-operations", "--to", str(output), "--quiet"],
        obj={SETTINGS_KEY: settings},
    )
    assert result.exit_code == 1
    assert "fetch market-orders --region-id 10000002" in result.output
    assert not output.parent.exists()
    connection.assert_not_called()
