#!/usr/bin/env bash
#
# Bump project version and push the bump commit.

set -e

cd "$(dirname "$0")"

FORCE=false

usage() {
    echo "Usage: $0 [options] VERSION"
    echo
    echo "VERSION:"
    echo "  major: bump major version number"
    echo "  minor: bump minor version number"
    echo "  patch: bump patch version number"
    echo
    echo "Options:"
    echo "  -f, --force:  skip confirmation prompt"
    echo "  -h, --help:   show this help message"
    echo
    exit 1
}

# parse args
while [ "$#" -gt 0 ]; do
    case "$1" in
    -f | --force)
        FORCE=true
        shift
        ;;
    -h | --help)
        usage
        ;;
    *)
        break
        ;;
    esac
done

if [ "$#" -ne 1 ]; then
    usage
fi

if [ "$1" != "major" ] && [ "$1" != "minor" ] && [ "$1" != "patch" ]; then
    usage
fi

current_branch="$(git rev-parse --abbrev-ref HEAD)"
if [ "$current_branch" = "HEAD" ]; then
    echo "Error: detached HEAD is not allowed for bump."
    exit 1
fi

if ! git diff-index --quiet HEAD -- && [ "$FORCE" = false ]; then
    echo "Error: git is not clean. Please commit all changes first."
    exit 1
fi

if ! command -v uv > /dev/null 2>&1; then
    echo "Error: uv is not installed. Please install uv from https://docs.astral.sh/uv/"
    exit 1
fi

echo "Would bump version:"
uv version --bump "$1" --dry-run

if [ "$FORCE" = false ]; then
    read -p "Do you want to bump and commit? [yY] " -n 1 -r
    echo
else
    REPLY="y"
fi
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    uv version --bump "$1"
    new_version="$(uv version --short)"

    git add pyproject.toml uv.lock
    git commit -m "bump version to $new_version"
    git push origin "$current_branch"

    echo "Bumped to $new_version and pushed branch '$current_branch'."
else
    echo "Aborted."
    exit 1
fi
