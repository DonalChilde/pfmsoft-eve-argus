#!/usr/bin/env bash
# Run sequentially, continuing after failures and reporting a nonzero final status.
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
