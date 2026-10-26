"""Tests for shared Markdown report formatting."""

from unittest.mock import Mock

import pytest

from pfmsoft.eve_argus.helpers import markdown


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("", ""),
        ("# Report\n\n\nText   \n", "# Report\n\nText\n"),
        (
            "| Name | Count |\n|---|---|\n| A | 1 |\n",
            "| Name | Count |\n| ---- | ----- |\n| A    | 1     |\n",
        ),
    ],
)
def test_format_markdown(source: str, expected: str) -> None:
    """Normalize whitespace and align Markdown tables without losing their syntax."""
    result = markdown.format_markdown(source)

    assert result == expected
    assert markdown.format_markdown(result) == result


def test_format_markdown_uses_table_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    """Forward Markdown to mdformat with the established table extension."""
    formatter = Mock(return_value="formatted\n")
    monkeypatch.setattr(markdown, "mdformat_text", formatter)

    assert markdown.format_markdown("source") == "formatted\n"
    formatter.assert_called_once_with("source", extensions=["tables"])


def test_format_markdown_propagates_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Do not hide formatter failures or return unformatted success-shaped output."""
    formatter = Mock(side_effect=ValueError("formatting failed"))
    monkeypatch.setattr(markdown, "mdformat_text", formatter)

    with pytest.raises(ValueError, match="formatting failed"):
        markdown.format_markdown("source")
