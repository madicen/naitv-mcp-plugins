#!/usr/bin/env bash
# Run ./scripts/test.sh for every plugins/*/plugin.json (catalog gate).
# Usage: ./scripts/test_all.sh
# Env: RUN_L4=1 forwards to each plugin that enables layers.l4.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FAILED=""
COUNT=0
while IFS= read -r plugin; do
  [[ -z "$plugin" ]] && continue
  COUNT=$((COUNT + 1))
  echo
  echo "######## $plugin ########"
  if ! "$ROOT/scripts/test.sh" "$plugin"; then
    FAILED="${FAILED} ${plugin}"
  fi
done < <(python3 "$ROOT/testing/plugin_harness.py" list)

if [[ "$COUNT" -eq 0 ]]; then
  echo "error: no plugins with plugins/*/plugin.json" >&2
  exit 2
fi

echo
if [[ -n "$FAILED" ]]; then
  echo "FAILED:${FAILED}" >&2
  exit 1
fi
echo "All ${COUNT} plugins passed"
