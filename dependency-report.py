# /// script
# requires-python = ">=3.11"
# dependencies = ["packaging"]
# ///
"""List dependencies from a pyproject.toml.

Dependencies are grouped by source, with both "name  version-range" pairs and a
space-separated name-only list per group.

Covers:
  - [project] dependencies                (standard deps)
  - [project.optional-dependencies]       (extras, PEP 621)
  - [dependency-groups]                   (PEP 735, what `uv` reads for dev/test groups)

Intended use: copy the space-separated name list for a group and feed it to
`uv remove <names>` and `uv add <names>` to bump minimum versions, since uv has no built-in
"upgrade my pyproject.toml floors" command.

Usage:
    uv run dependency-report.py [path-to-directory-or-pyproject.toml]
    uv run dependency-report.py --check-latest [path-to-directory-or-pyproject.toml]
    uv remove <names>  # to remove old versions
    uv add <names>     # to add new versions
    uv remove --dev <names>  # to remove old versions from dev/test groups
    uv add --dev <names>     # to add new versions to dev/test groups

If no path is given, searches the current working directory (and then
walks upward through parent directories) for a pyproject.toml.
"""

import argparse
import json
import sys
import tomllib
import urllib.request
from pathlib import Path
from urllib.error import HTTPError, URLError

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name


def find_pyproject(start: Path) -> Path:
    """Locate pyproject.toml starting at `start`, walking up if needed."""
    if start.is_file():
        return start

    for directory in [start, *start.resolve().parents]:
        candidate = directory / "pyproject.toml"
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(
        f"No pyproject.toml found in {start.resolve()} or any parent directory."
    )


def parse_requirement(raw: str) -> tuple[str, str]:
    """Return (name, version-range-string) for a PEP 508 requirement string.

    Falls back to the raw string as the "name" if it can't be parsed
    (e.g. it's a `{ include-group = "..." }` marker that slipped through,
    or some other non-standard entry).
    """
    try:
        req = Requirement(raw)
    except InvalidRequirement:
        return raw, ""

    name = req.name
    if req.extras:
        name += f"[{','.join(sorted(req.extras))}]"

    specifier = str(req.specifier) if req.specifier else "(no version pin)"
    if req.marker:
        specifier += f"; {req.marker}"

    return name, specifier


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the dependency report script."""
    parser = argparse.ArgumentParser(
        description=(
            "List dependencies from a pyproject.toml and optionally look up the latest "
            "published PyPI version for each package."
        )
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to a pyproject.toml or directory to search for one.",
    )
    parser.add_argument(
        "--check-latest",
        action="store_true",
        help="Check the latest published version from PyPI for each dependency.",
    )
    return parser.parse_args(argv)


def latest_pypi_version(package_name: str) -> str | None:
    """Return the latest published PyPI version for a package, or None on failure."""
    normalized = canonicalize_name(package_name)
    url = f"https://pypi.org/pypi/{normalized}/json"

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            payload = json.load(response)
    except HTTPError, OSError, TimeoutError, URLError, ValueError:
        return None

    info = payload.get("info", {})
    return info.get("version")


def print_group(
    title: str,
    raw_entries: list[str],
    *,
    check_latest: bool = False,
) -> None:
    """Print grouped dependency info, with optional latest PyPI versions."""
    print(f"\n=== {title} ({len(raw_entries)}) ===")
    if not raw_entries:
        print("  (none)")
        return

    parsed = [parse_requirement(e) for e in raw_entries]
    name_width = max(len(name) for name, _ in parsed)

    for name, version_range in parsed:
        package_name = name.split("[", 1)[0]
        latest = ""
        if check_latest:
            latest_version = latest_pypi_version(package_name)
            if latest_version is None:
                latest = "   latest: unavailable (offline or PyPI lookup failed)"
            else:
                latest = f"   latest: {latest_version}"
        print(f"  {name.ljust(name_width)}   {version_range}{latest}")

    names_only = [name.split("[", 1)[0] for name, _ in parsed]
    print(f"\n  names: {' '.join(names_only)}")


def main() -> None:
    """Main entry point: find pyproject.toml, read dependencies, and print them."""
    args = parse_args()
    target = Path(args.path)

    try:
        pyproject_path = find_pyproject(target)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading: {pyproject_path.resolve()}")

    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)

    project = data.get("project", {})

    # Standard [project] dependencies
    print_group(
        "project.dependencies",
        project.get("dependencies", []),
        check_latest=args.check_latest,
    )

    # [project.optional-dependencies] (extras) - keyed by extra name
    optional_deps = project.get("optional-dependencies", {})
    for extra_name, entries in optional_deps.items():
        print_group(
            f"project.optional-dependencies.{extra_name}",
            entries,
            check_latest=args.check_latest,
        )

    # [dependency-groups] (PEP 735) - keyed by group name. Entries can be
    # plain requirement strings OR {"include-group": "other-group"} dicts;
    # the latter are filtered out of the printed list (and noted) since
    # they aren't installable packages themselves.
    dependency_groups = data.get("dependency-groups", {})
    for group_name, entries in dependency_groups.items():
        str_entries = [e for e in entries if isinstance(e, str)]
        includes: list[str] = [
            e["include-group"]
            for e in entries
            if isinstance(e, dict) and "include-group" in e
        ]
        print_group(
            f"dependency-groups.{group_name}",
            str_entries,
            check_latest=args.check_latest,
        )
        if includes:
            print(f"  (also includes group(s): {', '.join(includes)})")

    if not project.get("dependencies") and not optional_deps and not dependency_groups:
        print("\nNo dependencies found under [project] or [dependency-groups].")


if __name__ == "__main__":
    main()
