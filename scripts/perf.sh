#!/usr/bin/env bash
# Nightly / release L3 perf gate for a plugin (default: structural-anchor).
# Usage: ./scripts/perf.sh [plugin] [-- files args passed to run_perf.py...]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PLUGIN="${1:-structural-anchor}"
if [[ $# -gt 0 ]]; then
  shift
fi

exec python3 "$ROOT/testing/perf/run_perf.py" "$PLUGIN" "$@"
