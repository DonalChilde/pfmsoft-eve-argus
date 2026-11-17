"""Verify PI directory generation, overwrite protection, and visible failures."""

from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

import pytest
from jinja2 import TemplateError
from typer.testing import CliRunner
from whenever import Instant

from pfmsoft.eve_argus.cli import app
from pfmsoft.eve_argus.cli.reports import planetary_interaction as command
from pfmsoft.eve_argus.dynamic.models import MarketOrdersDataset, MarketOrdersResponse
from pfmsoft.eve_argus.pi.catalog import load_catalog
from pfmsoft.eve_argus.reports.pi_browser import (
    PiMarketInputs,
    collect_pi_market_inputs,
)
from pfmsoft.eve_argus.reports.pi_browser_render import BROWSER_FILES
from pfmsoft.eve_argus.settings import SETTINGS_KEY, EveArgusSettings


@pytest.fixture
def collected() -> PiMarketInputs:
    """Keep empty market snapshots explicit and bypass all external resources."""
    response = MarketOrdersResponse(
        response_metadata_id=7,
        received_at="2026-11-17T10:00:00Z",
        expires_at="2026-11-17T11:00:00Z",
        argus_expires_at=None,
        region_id=10000002,
    )
    return collect_pi_market_inputs(
        catalog=load_catalog(),
        response=response,
        orders=MarketOrdersDataset(
            response_metadata_id=7,
            received_at=response.received_at,
            expires_at=response.expires_at,
            argus_expires_at=None,
            region_id=response.region_id,
            records={},
        ),
        history=None,
        generated_at=Instant.parse_iso("2026-11-17T12:00:00Z"),
    )


def test_cli_generates_complete_directory_and_retains_quiet_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, collected: PiMarketInputs
) -> None:
    """Quiet output still reports expired/missing sources, with no external I/O."""
    collector = Mock(return_value=collected)
    monkeypatch.setattr(command, "_collect_inputs", collector)
    destination = tmp_path / "browser"
    result = CliRunner().invoke(
        app,
        ["reports", "planetary-interaction", "--to", str(destination), "--quiet"],
        obj={SETTINGS_KEY: Mock(spec=EveArgusSettings)},
    )
    assert result.exit_code == 0, result.output
    assert {path.name for path in destination.iterdir()} == set(BROWSER_FILES)
    assert "Warning:" in result.output
    assert "expired" in result.output
    assert "Open" not in result.output


def test_existing_asset_fails_before_collection_and_overwrite_preserves_unrelated_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, collected: PiMarketInputs
) -> None:
    """Every asset participates in preflight, not just the entry HTML."""
    (tmp_path / "engine.js").write_text("existing", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("keep", encoding="utf-8")
    collector = Mock(return_value=collected)
    monkeypatch.setattr(command, "_collect_inputs", collector)
    arguments = ["reports", "planetary-interaction", "--to", str(tmp_path)]
    settings = {SETTINGS_KEY: Mock(spec=EveArgusSettings)}
    failure = CliRunner().invoke(app, arguments, obj=settings)
    assert failure.exit_code == 1
    assert "overwrite" in failure.output
    collector.assert_not_called()
    success = CliRunner().invoke(app, [*arguments, "--overwrite"], obj=settings)
    assert success.exit_code == 0, success.output
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "keep"
    assert (tmp_path / "engine.js").read_text(encoding="utf-8") != "existing"


@pytest.mark.parametrize("rate", ["NaN", "-1", "101"])
def test_invalid_tax_does_not_collect_or_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rate: str
) -> None:
    """The CLI parses decimal percentages without accepting invalid monetary inputs."""
    collector = Mock()
    monkeypatch.setattr(command, "_collect_inputs", collector)
    destination = tmp_path / "not-created"
    result = CliRunner().invoke(
        app,
        [
            "reports",
            "planetary-interaction",
            "--to",
            str(destination),
            "--tax-percent",
            rate,
        ],
        obj={SETTINGS_KEY: Mock(spec=EveArgusSettings)},
    )
    assert result.exit_code != 0
    collector.assert_not_called()
    assert not destination.exists()


def test_collection_failure_does_not_create_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing stored sources fail visibly instead of writing an empty success page."""
    monkeypatch.setattr(
        command,
        "_collect_inputs",
        Mock(side_effect=ValueError("Fetch market-orders first.")),
    )
    destination = tmp_path / "not-created"
    result = CliRunner().invoke(
        app,
        ["reports", "planetary-interaction", "--to", str(destination)],
        obj={SETTINGS_KEY: Mock(spec=EveArgusSettings)},
    )
    assert result.exit_code == 1
    assert "Fetch market-orders" in result.output
    assert not destination.exists()


def test_snapshot_selection_uses_only_jita_and_one_regional_history_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, collected: PiMarketInputs
) -> None:
    """Metadata selection, filtered reads, and history remain linked and read-only."""
    settings = Mock(spec=EveArgusSettings)
    settings.argus_dynamic_database = tmp_path / "dynamic.sqlite"
    settings.market_history_database = tmp_path / "history.sqlite"
    settings.argus_dynamic_database.touch()
    settings.market_history_database.touch()
    connection = Mock()
    manager = Mock(return_value=nullcontext(connection))
    monkeypatch.setattr(command, "db_connection_manager", manager)
    monkeypatch.setattr(
        command, "Instant", Mock(now=Mock(return_value=collected.generated_at))
    )
    responses = Mock(return_value=[collected.response])
    orders = Mock(return_value=())
    newest = Mock(return_value="2026-11-16")
    history = Mock(return_value=())
    monkeypatch.setattr(command.dynamic_read, "market_orders_responses", responses)
    monkeypatch.setattr(command.dynamic_read, "market_orders_filtered", orders)
    monkeypatch.setattr(command.history_read, "newest_market_history_date", newest)
    monkeypatch.setattr(command.history_read, "market_history_date_range", history)
    renderer = Mock(wraps=command.render_pi_browser)
    monkeypatch.setattr(command, "render_pi_browser", renderer)
    invocation = CliRunner().invoke(
        app,
        ["reports", "planetary-interaction", "--to", str(tmp_path / "browser")],
        obj={SETTINGS_KEY: settings},
    )
    assert invocation.exit_code == 0, invocation.output
    result = renderer.call_args.args[0]
    assert isinstance(result, PiMarketInputs)
    responses.assert_called_once_with(connection, region_id=collected.hub.region_id)
    assert orders.call_count == 83
    for call in orders.call_args_list:
        assert call.args == (connection, collected.response.response_metadata_id)
        assert call.kwargs["location_id"] == collected.hub.station_id
    newest.assert_called_once_with(
        connection, region_id=collected.hub.region_id, before="2026-11-17"
    )
    assert history.call_count == 83
    assert all(call.kwargs["end"] == "2026-11-07" for call in history.call_args_list)
    assert all(call.kwargs["read_only"] is True for call in manager.call_args_list)
    assert result.response is collected.response


def test_render_failure_does_not_create_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, collected: PiMarketInputs
) -> None:
    """Render every asset before creating files and surface template failures."""
    monkeypatch.setattr(command, "_collect_inputs", Mock(return_value=collected))
    monkeypatch.setattr(
        command,
        "render_pi_browser",
        Mock(side_effect=TemplateError("Invalid template.")),
    )
    destination = tmp_path / "not-created"
    result = CliRunner().invoke(
        app,
        ["reports", "planetary-interaction", "--to", str(destination)],
        obj={SETTINGS_KEY: Mock(spec=EveArgusSettings)},
    )
    assert result.exit_code == 1
    assert "Invalid template" in result.output
    assert not destination.exists()


def test_overwrite_never_follows_an_asset_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An existing asset cannot redirect writes into an unrelated file."""
    destination = tmp_path / "browser"
    destination.mkdir()
    target = tmp_path / "unrelated.txt"
    target.write_text("unchanged", encoding="utf-8")
    (destination / "engine.js").symlink_to(target)
    collector = Mock()
    monkeypatch.setattr(command, "_collect_inputs", collector)
    result = CliRunner().invoke(
        app,
        ["reports", "planetary-interaction", "--to", str(destination), "--overwrite"],
        obj={SETTINGS_KEY: Mock(spec=EveArgusSettings)},
    )
    assert result.exit_code == 1
    collector.assert_not_called()
    assert target.read_text(encoding="utf-8") == "unchanged"


def test_write_failure_reports_error_and_leaves_prior_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, collected: PiMarketInputs
) -> None:
    """A collision after preflight is a failure, not an atomic rollback."""
    destination = tmp_path / "browser"

    def collect_with_collision(_settings: EveArgusSettings) -> PiMarketInputs:
        destination.mkdir()
        (destination / "engine.js").mkdir()
        return collected

    monkeypatch.setattr(command, "_collect_inputs", collect_with_collision)
    result = CliRunner().invoke(
        app,
        ["reports", "planetary-interaction", "--to", str(destination)],
        obj={SETTINGS_KEY: Mock(spec=EveArgusSettings)},
    )
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "engine.js" in result.output
    assert (destination / "index.html").is_file()
    assert not (destination / "app.js").exists()
