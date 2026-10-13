#!/usr/bin/env bash
# Create plugins/<name>/ with plugin.json + harness.json stubs.
# Usage: ./scripts/scaffold_plugin.sh <plugin-name> [json_tools|rules_only|mixed]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="${1:-}"
PROFILE="${2:-json_tools}"

if [[ -z "$NAME" ]]; then
  echo "usage: $0 <plugin-name> [json_tools|rules_only|mixed]" >&2
  exit 2
fi

DIR="$ROOT/plugins/$NAME"
if [[ -e "$DIR/plugin.json" ]]; then
  echo "error: already exists: $DIR/plugin.json" >&2
  exit 1
fi

mkdir -p "$DIR/tests"

# Prefer migrating a legacy flat manifest if present.
if [[ -f "$ROOT/plugins/$NAME.json" ]]; then
  cp "$ROOT/plugins/$NAME.json" "$DIR/plugin.json"
  echo "copied plugins/$NAME.json -> plugins/$NAME/plugin.json"
else
  cat >"$DIR/plugin.json" <<EOF
{
  "name": "$NAME",
  "version": "0.1.0",
  "description": "TODO: describe $NAME",
  "author": "madicen",
  "tags": ["$NAME"],
  "entries": []
}
EOF
fi

case "$PROFILE" in
  rules_only)
    cat >"$DIR/harness.json" <<EOF
{
  "profile": "rules_only",
  "layers": { "l1": true, "l2": false, "l3_golden": false, "l4": false, "l5": false }
}
EOF
    ;;
  mixed)
    cat >"$DIR/harness.json" <<EOF
{
  "profile": "mixed",
  "layers": { "l1": true, "l2": true, "l3_golden": true, "l4": true, "l5": false }
}
EOF
    ;;
  *)
    MOD="${NAME//-/_}"
    # lazy: omit coverage until L1 tests import the module (set module + fail_under then)
    cat >"$DIR/harness.json" <<EOF
{
  "profile": "json_tools",
  "coverage": {},
  "layers": { "l1": true, "l2": true, "l3_golden": true, "l4": true, "l5": false },
  "perf": { "enabled": false },
  "l5": { "treatment_plugins": ["$NAME"], "tool_names": [] }
}
EOF
    ;;
esac

cat >"$DIR/tests/test_manifest.py" <<EOF
"""Smoke: plugin manifest loads and passes entry lint."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_entry_lint() -> None:
    r = subprocess.run(
        [sys.executable, str(REPO / "testing/contract/run_entry_lint.py"), "$NAME"],
        cwd=str(REPO),
        check=False,
    )
    assert r.returncode == 0
EOF

echo "Created $DIR"
echo "Next: add entries to plugin.json; for tools add schemas under testing/contract/schemas/"
echo "Run: ./scripts/test.sh $NAME"
