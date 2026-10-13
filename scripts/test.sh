#!/usr/bin/env bash
# Run enabled layers for one plugin (see plugins/<name>/harness.json).
# Usage: ./scripts/test.sh <plugin-name>
# Env: RUN_L4=1 to force L4 when harness layers.l4 is true.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PLUGIN="${1:-}"
if [[ -z "$PLUGIN" ]]; then
  echo "usage: $0 <plugin-name>" >&2
  echo "testable:" >&2
  python3 "$ROOT/testing/plugin_harness.py" list >&2 || true
  exit 2
fi

PLUGIN_DIR="$ROOT/plugins/$PLUGIN"
if [[ ! -f "$PLUGIN_DIR/plugin.json" ]]; then
  echo "error: missing $PLUGIN_DIR/plugin.json (use ./scripts/scaffold_plugin.sh $PLUGIN)" >&2
  exit 2
fi

# shellcheck disable=SC1090
eval "$(python3 "$ROOT/testing/plugin_harness.py" dump "$PLUGIN")"

if [[ ! -d "$ROOT/.venv" ]]; then
  python3 -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/pip" install -q pytest
fi
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"

if [[ "${LAYER_L1:-1}" == "1" ]]; then
  echo "=== L1 entry lint ($PLUGIN) ==="
  python "$ROOT/testing/contract/run_entry_lint.py" "$PLUGIN"

    if [[ -d "$PLUGIN_DIR/tests" ]] && compgen -G "$PLUGIN_DIR/tests/test_*.py" >/dev/null; then
    echo
    echo "=== L1 unit ($PLUGIN) ==="
    PYTEST_MARK="not perf"
    # Coverage only when the configured module file exists under COV_PATH.
    if [[ -n "${COV_MODULE:-}" && -n "${COV_PATH:-}" && -f "${COV_PATH}/${COV_MODULE}.py" ]]; then
      "$ROOT/.venv/bin/pip" install -q pytest-cov >/dev/null
      PYTHONPATH="$COV_PATH${PYTHONPATH:+:$PYTHONPATH}" python -m pytest "$PLUGIN_DIR/tests" -q \
        -m "$PYTEST_MARK" \
        --cov="$COV_MODULE" --cov-report=term-missing:skip-covered \
        --cov-fail-under="${COV_FAIL_UNDER:-80}"
    else
      echo "note: no coverage module on disk yet; running tests without coverage gate"
      python -m pytest "$PLUGIN_DIR/tests" -q -m "$PYTEST_MARK"
    fi
  elif [[ "$PROFILE" == "rules_only" ]]; then
    echo "note: rules_only — entry lint only (no pytest suite)"
  else
    echo "note: no plugins/$PLUGIN/tests/test_*.py yet"
  fi
fi

if [[ "${LAYER_L2:-0}" == "1" ]]; then
  echo
  echo "=== L2 contract ($PLUGIN) ==="
  set +e
  python "$ROOT/testing/contract/run_contract.py" --use-repo-tools "$PLUGIN"
  L2_RC=$?
  set -e
  if [[ "$L2_RC" -eq 0 ]]; then
    echo "L2: all contract checks passed"
  elif [[ "$L2_RC" -eq 2 ]]; then
    echo "L2: not implemented / incomplete (exit 2) — draft OK; add schemas+fixtures to harden" >&2
    # Soft for drafts: do not fail the default gate on pure NOT IMPLEMENTED.
  else
    echo "L2: contract failures (exit $L2_RC)" >&2
    exit "$L2_RC"
  fi
fi

if [[ "${LAYER_L3_GOLDEN:-0}" == "1" && -d "$ROOT/testing/golden/$PLUGIN" ]]; then
  echo
  echo "=== L3 golden ($PLUGIN) ==="
  python "$ROOT/testing/golden/run_golden.py" "$PLUGIN"
fi

if [[ "${RUN_L4:-}" == "1" && "${LAYER_L4:-0}" == "1" ]]; then
  echo
  "$ROOT/scripts/l4.sh" "$PLUGIN"
fi
