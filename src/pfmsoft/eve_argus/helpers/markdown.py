"""Escape text embedded in Markdown table cells and headings."""

from html import escape


def markdown_cell(value: object) -> str:
    """Escape Markdown/HTML syntax and render embedded newlines as HTML breaks."""
    text = escape(str(value), quote=False).replace("\\", "\\\\")
    for character in ("|", "`", "[", "]", "*", "_"):
        text = text.replace(character, "\\" + character)
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
