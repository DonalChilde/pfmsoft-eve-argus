#!/usr/bin/env bash
#
# Create and push a release tag from a required branch.

set -e

cd "$(dirname "$0")"

FORCE=false
RELEASABLE_BRANCH="${RELEASABLE_BRANCH:-main}"

usage() {
    echo "Usage: $0 [options] [VERSION]"
    echo
    echo "VERSION (optional):"
    echo "  1.2.3 or v1.2.3"
    echo "  If omitted, version is read from 'uv version --short'."
    echo
    echo "Options:"
    echo "  -f, --force:  skip confirmation prompt"
    echo "  -h, --help:   show this help message"
    echo
    echo "Environment variables:"
    echo "  RELEASABLE_BRANCH: required git branch for tagging (default: main)"
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

if [ "$#" -gt 1 ]; then
    usage
fi

current_branch="$(git rev-parse --abbrev-ref HEAD)"
if [ "$current_branch" = "HEAD" ]; then
    echo "Error: detached HEAD is not allowed for tagging. Check out '$RELEASABLE_BRANCH'."
    exit 1
fi

if [ "$current_branch" != "$RELEASABLE_BRANCH" ]; then
    echo "Error: tagging must be run on branch '$RELEASABLE_BRANCH' (current: '$current_branch')."
    exit 1
fi

if ! git diff-index --quiet HEAD -- && [ "$FORCE" = false ]; then
    echo "Error: git is not clean. Please commit all changes first."
    exit 1
fi

if [ "$#" -eq 1 ]; then
    version="$1"
else
    if ! command -v uv > /dev/null 2>&1; then
        echo "Error: uv is not installed. Please install uv from https://docs.astral.sh/uv/"
        exit 1
    fi
    version="$(uv version --short)"
fi

version="${version#v}"
tag="v$version"

if git rev-parse "$tag" > /dev/null 2>&1; then
    echo "Error: local tag '$tag' already exists."
    exit 1
fi

if git ls-remote --tags origin "refs/tags/$tag" | grep -q .; then
    echo "Error: remote tag '$tag' already exists on origin."
    exit 1
fi

echo "Would create tag '$tag' on branch '$RELEASABLE_BRANCH' at commit:"
git rev-parse --short HEAD

if [ "$FORCE" = false ]; then
    read -p "Do you want to create and push this tag? [yY] " -n 1 -r
    echo
else
    REPLY="y"
fi
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    git tag -a "$tag" -m "$tag"
    git push origin "$RELEASABLE_BRANCH"
    git push origin "$tag"

    echo "Pushed branch '$RELEASABLE_BRANCH' and tag '$tag'."
else
    echo "Aborted."
    exit 1
fi
