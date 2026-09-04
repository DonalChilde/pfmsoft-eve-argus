"""Tests for the corporation owned-vs-missing BPO Markdown report."""

from whenever import Instant

from pfmsoft.eve_argus.reports.corp_missing_bpo import (
    CorpBpoReport,
    MissingBpoRow,
    OwnedBpoRow,
)
from pfmsoft.eve_argus.reports.corp_missing_bpo_markdown import (
    render_corp_bpo_report_markdown,
)

REPORT_TIME = Instant.parse_iso("2026-09-04T12:00:00Z")


def make_owned(
    *,
    type_id: int = 1000,
    name: str = "Vexor Blueprint",
    market_path: str = "Blueprints > Ship Blueprints > Frigate Blueprints",
    quantity: int = 1,
    material_efficiency: int = 10,
    time_efficiency: int = 18,
) -> OwnedBpoRow:
    """Build an owned row with sensible defaults."""
    return OwnedBpoRow(
        type_id=type_id,
        name=name,
        market_path=market_path,
        quantity=quantity,
        material_efficiency=material_efficiency,
        time_efficiency=time_efficiency,
    )


def make_missing(
    *,
    type_id: int = 1001,
    name: str = "Rifter Blueprint",
    market_path: str = "Blueprints > Ship Blueprints > Frigate Blueprints",
    base_price: float | None = 250000.0,
) -> MissingBpoRow:
    """Build a missing row with sensible defaults."""
    return MissingBpoRow(
        type_id=type_id,
        name=name,
        market_path=market_path,
        base_price=base_price,
    )


def render(report: CorpBpoReport) -> str:
    """Render a report at the fixed report timestamp."""
    return render_corp_bpo_report_markdown(report, report_generated_at=REPORT_TIME)


def test_report_includes_header_and_sections() -> None:
    """The report contains its header and both required sections."""
    output = render(CorpBpoReport(corporation_id=98777771))

    assert "# Corporation 98777771 Blueprint Originals" in output
    assert "Generated at (UTC): `2026-09-04T12:00:00Z`" in output
    assert "## Owned Blueprints" in output
    assert "## Missing Blueprints" in output


def test_owned_row_appears_in_owned_table() -> None:
    """An owned blueprint is rendered in the owned table, not the missing table."""
    output = render(CorpBpoReport(corporation_id=98777771, owned=[make_owned()]))

    owned_section = output.split("## Owned Blueprints", 1)[1].split(
        "## Missing Blueprints", 1
    )[0]
    missing_section = output.split("## Missing Blueprints", 1)[1]
    assert "Vexor Blueprint" in owned_section
    assert "Vexor Blueprint" not in missing_section


def test_missing_row_appears_in_missing_table() -> None:
    """A missing blueprint is rendered in the missing table, not the owned table."""
    output = render(CorpBpoReport(corporation_id=98777771, missing=[make_missing()]))

    owned_section = output.split("## Owned Blueprints", 1)[1].split(
        "## Missing Blueprints", 1
    )[0]
    missing_section = output.split("## Missing Blueprints", 1)[1]
    assert "Rifter Blueprint" in missing_section
    assert "Rifter Blueprint" not in owned_section


def test_missing_row_with_no_base_price_renders_placeholder() -> None:
    """A missing blueprint without a base price renders a placeholder, not 'None'."""
    output = render(
        CorpBpoReport(corporation_id=98777771, missing=[make_missing(base_price=None)])
    )

    assert "None" not in output


def test_owned_groups_blueprints_under_each_market_path() -> None:
    """Owned blueprints are grouped under each market path, listed once."""
    output = render(
        CorpBpoReport(
            corporation_id=98777771,
            owned=[
                make_owned(),
                make_owned(type_id=1002, name="Atron Blueprint", material_efficiency=4),
                make_owned(
                    type_id=2000,
                    name="Some Other Blueprint",
                    market_path="Blueprints > Other",
                ),
            ],
        )
    )

    owned_section = output.split("## Owned Blueprints", 1)[1].split(
        "## Missing Blueprints", 1
    )[0]
    # The shared path is listed once as a heading, with both blueprints beneath it.
    assert (
        owned_section.count("### Blueprints > Ship Blueprints > Frigate Blueprints")
        == 1
    )
    assert "Vexor Blueprint" in owned_section
    assert "Atron Blueprint" in owned_section
    # Rows no longer carry the market path inline.
    assert "| Vexor Blueprint | Blueprints >" not in owned_section
    # A second group gets its own heading.
    assert "### Blueprints > Other" in owned_section


def test_market_path_groups_sorted_alphabetically() -> None:
    """Market path groups render in alphabetical order."""
    output = render(
        CorpBpoReport(
            corporation_id=98777771,
            owned=[
                make_owned(
                    type_id=2000,
                    name="Zebra Blueprint",
                    market_path="Blueprints > Zulu",
                ),
                make_owned(
                    type_id=1000,
                    name="Vexor Blueprint",
                    market_path="Blueprints > Alpha",
                ),
            ],
        )
    )

    owned_section = output.split("## Owned Blueprints", 1)[1].split(
        "## Missing Blueprints", 1
    )[0]
    assert owned_section.index("### Blueprints > Alpha") < owned_section.index(
        "### Blueprints > Zulu"
    )


def test_missing_groups_blueprints_under_each_market_path() -> None:
    """Missing blueprints are grouped under each market path, listed once."""
    output = render(
        CorpBpoReport(
            corporation_id=98777771,
            missing=[
                make_missing(),
                make_missing(type_id=1002, name="Atron Blueprint"),
            ],
        )
    )

    missing_section = output.split("## Missing Blueprints", 1)[1]
    assert (
        missing_section.count("### Blueprints > Ship Blueprints > Frigate Blueprints")
        == 1
    )
    assert "Rifter Blueprint" in missing_section
    assert "Atron Blueprint" in missing_section
