"""Shared helpers for static database exports."""

from collections.abc import Mapping, Sequence
from pathlib import Path

from rich.console import Console


def check_destination(destination: Path) -> None:
    """Ensure the export destination is either absent or a directory."""
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"Export destination is not a directory: {destination}")


def check_output_paths(*, paths: Sequence[Path], overwrite: bool) -> None:
    """Validate output paths before writing any export files."""
    for path in paths:
        if path.exists() and (not overwrite or not path.is_file()):
            raise ValueError(
                f"Export path already exists: {path}. "
                "Use --overwrite to replace existing files."
            )


def write_outputs(
    *,
    contents: Mapping[Path, str],
    overwrite: bool,
    messenger: Console,
) -> None:
    """Write pre-rendered export files and report their paths."""
    if not contents:
        raise ValueError("No export files were provided.")
    destination = next(iter(contents)).parent
    destination.mkdir(parents=True, exist_ok=True)
    for path, content in contents.items():
        with path.open(
            "w" if overwrite else "x", encoding="utf-8", newline=""
        ) as stream:
            stream.write(content)
        messenger.print(f"Wrote {path}", markup=False)


def export_file_name(*, stem: str, build_number: int, suffix: str) -> str:
    """Return a static export filename that identifies its SDE build."""
    return f"{stem}-build-{build_number}.{suffix}"
