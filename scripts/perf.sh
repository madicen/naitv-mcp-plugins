#!/usr/bin/env bash
# Nightly / release L3 perf gate (requires harness.json perf.enabled).
# Usage: ./scripts/perf.sh <plugin> [-- args to run_perf.py...]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PLUGIN="${1:-}"
if [[ -z "$PLUGIN" ]]; then
  echo "usage: $0 <plugin-name> [-- run_perf args...]" >&2
  exit 2
fi
shift

exec python3 "$ROOT/testing/perf/run_perf.py" "$PLUGIN" "$@"
