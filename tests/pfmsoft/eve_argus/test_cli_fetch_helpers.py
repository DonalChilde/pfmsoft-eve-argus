"""Tests for shared fetch command helpers."""

from io import StringIO
from types import SimpleNamespace
from uuid import UUID

import pytest
import typer
from rich.console import Console

from pfmsoft.eve_argus.cli.fetch._helpers import (
    report_update_result,
    resolve_corporation_arguments,
)
from pfmsoft.eve_argus.dynamic.models import ResponseMetadata
from pfmsoft.eve_argus.fetch_esi.update import UpdateResult, UpdateStatus


def test_resolve_corporation_arguments_prefers_explicit_values() -> None:
    """Explicit corporation command arguments should override configured defaults."""
    default_credential_id = UUID("00000000-0000-0000-0000-000000000001")
    explicit_credential_id = UUID("00000000-0000-0000-0000-000000000002")
    settings = SimpleNamespace(
        corporation_id=100,
        character_id=200,
        credential_id=default_credential_id,
    )

    result = resolve_corporation_arguments(
        settings=settings,  # type: ignore[arg-type]
        corporation_id=0,
        character_id=300,
        credential_id=explicit_credential_id,
    )

    assert result == (0, 300, explicit_credential_id)


def test_resolve_corporation_arguments_uses_defaults() -> None:
    """Missing corporation command arguments should use configured defaults."""
    credential_id = UUID("00000000-0000-0000-0000-000000000001")
    settings = SimpleNamespace(
        corporation_id=100,
        character_id=200,
        credential_id=credential_id,
    )

    result = resolve_corporation_arguments(
        settings=settings,  # type: ignore[arg-type]
        corporation_id=None,
        character_id=None,
        credential_id=None,
    )

    assert result == (100, 200, credential_id)


def test_resolve_corporation_arguments_requires_credential() -> None:
    """The command should explain when no credential ID is configured."""
    settings = SimpleNamespace(corporation_id=100, character_id=200, credential_id=None)

    with pytest.raises(typer.BadParameter, match="--credential-id"):
        resolve_corporation_arguments(
            settings=settings,  # type: ignore[arg-type]
            corporation_id=None,
            character_id=None,
            credential_id=None,
        )


def test_report_update_result_reports_success() -> None:
    """Successful updates should report storage and return the new response."""
    output = StringIO()
    response = ResponseMetadata(
        response_metadata_id=1,
        received_at="2026-10-17T00:00:00Z",
        expires_at=None,
        argus_expires_at=None,
    )
    result = UpdateResult(
        status=UpdateStatus.UPDATED,
        previous_state=None,
        new_state=response,
    )

    actual = report_update_result(
        result,
        messenger=Console(file=output),
        dataset_name="market prices",
    )

    assert actual is response
    assert "Fetched and stored market prices." in output.getvalue()
    assert "expiration is unavailable" in output.getvalue()


def test_report_update_result_reports_cached_response() -> None:
    """Skipped updates should report that the stored response remains current."""
    output = StringIO()
    response = ResponseMetadata(
        response_metadata_id=1,
        received_at="2026-10-17T00:00:00Z",
        expires_at=None,
        argus_expires_at=None,
    )
    result = UpdateResult(
        status=UpdateStatus.SKIPPED,
        previous_state=response,
    )

    actual = report_update_result(
        result,
        messenger=Console(file=output),
        dataset_name="market prices",
    )

    assert actual is response
    assert "Using cached market prices" in output.getvalue()
    assert "stored dataset for market prices is already current" in output.getvalue()


def test_report_update_result_exits_for_failed_update() -> None:
    """Failed updates should print the failure and return a nonzero CLI exit."""
    output = StringIO()
    result = UpdateResult[ResponseMetadata](
        status=UpdateStatus.FAILED,
        previous_state=None,
        failure_message="ESI unavailable",
    )

    with pytest.raises(typer.Exit) as error:
        report_update_result(
            result,
            messenger=Console(file=output),
            dataset_name="market prices",
        )

    assert error.value.exit_code == 1
    assert "ESI unavailable" in output.getvalue()
