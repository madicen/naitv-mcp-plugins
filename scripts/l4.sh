#!/usr/bin/env bash
# L4: MCP integration through a real naitv-mcp serve (stdio).
# Usage: ./scripts/l4.sh [plugin-name]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PLUGIN="${1:-structural-anchor}"

if ! command -v naitv-mcp >/dev/null 2>&1; then
  echo "error: naitv-mcp not on PATH" >&2
  exit 2
fi

echo "=== L4 cross-plugin checks ==="
python3 "$ROOT/testing/integration/cross_plugin_check.py"

echo
echo "=== L4 MCP integration ($PLUGIN) ==="
python3 "$ROOT/testing/integration/run_l4.py" "$PLUGIN"
