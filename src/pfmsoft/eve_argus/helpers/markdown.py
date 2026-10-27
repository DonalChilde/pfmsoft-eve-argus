"""Format Markdown reports and escape embedded table cells and headings."""

from html import escape

from mdformat import text as mdformat_text  # type: ignore


def format_markdown(markdown: str) -> str:
    """Format Markdown with mdformat, preserving and aligning tables."""
    return mdformat_text(markdown, extensions=["tables"])


def markdown_cell(value: object) -> str:
    """Escape Markdown/HTML syntax and render embedded newlines as HTML breaks."""
    text = escape(str(value), quote=False).replace("\\", "\\\\")
    for character in ("|", "`", "[", "]", "*", "_"):
        text = text.replace(character, "\\" + character)
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
