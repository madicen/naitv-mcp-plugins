#!/usr/bin/env bash
# Run L1 (pytest) then L2 (contract) for one plugin.
# Usage: ./scripts/test.sh <plugin-name>
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PLUGIN="${1:-}"
if [[ -z "$PLUGIN" ]]; then
  echo "usage: $0 <plugin-name>" >&2
  exit 2
fi

PLUGIN_DIR="$ROOT/plugins/$PLUGIN"
if [[ ! -d "$PLUGIN_DIR" ]]; then
  echo "error: missing plugin directory: $PLUGIN_DIR" >&2
  exit 2
fi

if [[ ! -d "$ROOT/.venv" ]]; then
  python3 -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/pip" install -q pytest
fi
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"

echo "=== L1 unit ($PLUGIN) ==="
L1_ARGS=()
if [[ -d "$PLUGIN_DIR/tests" ]]; then
  L1_ARGS+=("$PLUGIN_DIR/tests")
else
  echo "error: no tests directory at $PLUGIN_DIR/tests" >&2
  exit 1
fi

# Coverage on plugin-local implementation when present; else tools/<plugin>.
COV_DIR=""
if [[ -f "$PLUGIN_DIR/structural_anchor.py" ]]; then
  COV_DIR="$PLUGIN_DIR"
elif [[ -f "$ROOT/tools/$PLUGIN/structural_anchor.py" ]]; then
  COV_DIR="$ROOT/tools/$PLUGIN"
fi

if [[ -n "$COV_DIR" ]]; then
  "$ROOT/.venv/bin/pip" install -q pytest-cov >/dev/null
  PYTHONPATH="$COV_DIR${PYTHONPATH:+:$PYTHONPATH}" python -m pytest "${L1_ARGS[@]}" -q \
    --cov=structural_anchor --cov-report=term-missing:skip-covered \
    --cov-fail-under=80
else
  echo "note: no implementation module found; running tests without coverage gate"
  python -m pytest "${L1_ARGS[@]}" -q
fi

echo
echo "=== L2 contract ($PLUGIN) ==="
set +e
python "$ROOT/testing/contract/run_contract.py" "$PLUGIN"
L2_RC=$?
set -e

if [[ "$L2_RC" -eq 0 ]]; then
  echo "L2: all contract checks passed"
  exit 0
elif [[ "$L2_RC" -eq 2 ]]; then
  echo "L2: unfinished / not implemented (see report above) — OK for draft plugins"
  exit 0
else
  echo "L2: contract failures (exit $L2_RC)" >&2
  exit "$L2_RC"
fi
