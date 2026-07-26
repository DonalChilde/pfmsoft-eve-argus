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
    uv remove <names>  # to remove old versions
    uv add <names>     # to add new versions
    uv remove --dev <names>  # to remove old versions from dev/test groups
    uv add --dev <names>     # to add new versions to dev/test groups

If no path is given, searches the current working directory (and then
walks upward through parent directories) for a pyproject.toml.
"""

import sys
import tomllib
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement


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


def print_group(title: str, raw_entries: list[str]) -> None:
    """Print a group of dependencies with both "name  version-range" and a space-separated name-only list."""
    print(f"\n=== {title} ({len(raw_entries)}) ===")
    if not raw_entries:
        print("  (none)")
        return

    parsed = [parse_requirement(e) for e in raw_entries]
    name_width = max(len(name) for name, _ in parsed)

    for name, version_range in parsed:
        print(f"  {name.ljust(name_width)}   {version_range}")

    names_only = [name.split("[", 1)[0] for name, _ in parsed]
    print(f"\n  names: {' '.join(names_only)}")


def main() -> None:
    """Main entry point: find pyproject.toml, read dependencies, and print them."""
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()

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
    print_group("project.dependencies", project.get("dependencies", []))

    # [project.optional-dependencies] (extras) - keyed by extra name
    optional_deps = project.get("optional-dependencies", {})
    for extra_name, entries in optional_deps.items():
        print_group(f"project.optional-dependencies.{extra_name}", entries)

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
        print_group(f"dependency-groups.{group_name}", str_entries)
        if includes:
            print(f"  (also includes group(s): {', '.join(includes)})")

    if not project.get("dependencies") and not optional_deps and not dependency_groups:
        print("\nNo dependencies found under [project] or [dependency-groups].")


if __name__ == "__main__":
    main()
