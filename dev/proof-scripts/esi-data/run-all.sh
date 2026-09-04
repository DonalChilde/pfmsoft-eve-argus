#!/usr/bin/env bash
# Run all ESI data proof scripts with `uv run` from the project root.
#
# Scripts run sequentially to be gentle on ESI rate limits. Files starting
# with an underscore (e.g. _shared.py) are helper modules and are skipped.
# A failure in one script does not stop the rest; failures are summarized
# at the end and cause a non-zero exit.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

cd "$PROJECT_ROOT"

FAILED=()
for script in "$SCRIPT_DIR"/*.py; do
    script_name="$(basename "$script")"
    if [[ "$script_name" == _* ]]; then
        continue
    fi
    echo "=== Running $script_name ==="
    if uv run "$script"; then
        echo "=== $script_name succeeded ==="
    else
        echo "=== $script_name FAILED ==="
        FAILED+=("$script_name")
    fi
    echo
done

if ((${#FAILED[@]})); then
    echo "Failed proof scripts:"
    printf ' - %s\n' "${FAILED[@]}"
    exit 1
fi
echo "All proof scripts succeeded."
