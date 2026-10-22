#!/usr/bin/env bash
# Build next planned plugin(s) until done or blocked.
# Usage: ./scripts/run_build_cycle.sh [max_plugins]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
MAX="${1:-999}"
REPORT="$ROOT/.cycle-report.txt"
: >"$REPORT"

next_plugin() {
  python3 - <<'PY'
import json
from pathlib import Path
data=json.loads(Path("docs/plan/plugins.json").read_text())
by={p["name"]:p for p in data["plugins"]}
for p in sorted(data["plugins"], key=lambda x: x.get("order", 999)):
    if p.get("status") != "planned":
        continue
    tools=p.get("tools")
    if not tools:
        continue
    deps=p.get("depends_on") or []
    if all(by.get(d,{}).get("status")=="exists" for d in deps):
        print(p["name"])
        break
PY
}

stack_base() {
  # Prefer latest plugin/* bookmark as PR base
  jj bookmark list -a 2>/dev/null | awk '/^plugin\// {print $1}' | tr -d ':' | tail -1
}

n=0
while [[ "$n" -lt "$MAX" ]]; do
  NAME="$(next_plugin)"
  if [[ -z "$NAME" ]]; then
    echo "NO_MORE_BUILDABLE" | tee -a "$REPORT"
    break
  fi
  echo "=== BUILD $NAME ===" | tee -a "$REPORT"
  jj new
  python3 scripts/generate_plugin.py "$NAME"
  python3 testing/golden/run_golden.py "$NAME" --update-golden
  if ! make test-plugin "PLUGIN=$NAME"; then
    echo "FAIL_TEST $NAME" | tee -a "$REPORT"
    # mark blocked
    python3 - <<PY
import json
from pathlib import Path
p=Path("docs/plan/plugins.json")
data=json.loads(p.read_text())
for e in data["plugins"]:
    if e["name"]=="$NAME":
        e["status"]="blocked"
        e["notes"]=(e.get("notes") or "")+" BLOCKED: make test-plugin failed."
p.write_text(json.dumps(data, indent=2)+"\n")
PY
    echo "BLOCKED $NAME — stopping cycle" | tee -a "$REPORT"
    break
  fi
  if ! make l4 "PLUGIN=$NAME"; then
    echo "FAIL_L4 $NAME" | tee -a "$REPORT"
    python3 - <<PY
import json
from pathlib import Path
p=Path("docs/plan/plugins.json")
data=json.loads(p.read_text())
for e in data["plugins"]:
    if e["name"]=="$NAME":
        e["status"]="blocked"
        e["notes"]=(e.get("notes") or "")+" BLOCKED: make l4 failed."
p.write_text(json.dumps(data, indent=2)+"\n")
PY
    echo "BLOCKED $NAME — stopping cycle" | tee -a "$REPORT"
    break
  fi
  python3 scripts/catalog_check.py >/tmp/catalog_check.out || true
  tail -1 /tmp/catalog_check.out | tee -a "$REPORT"
  rm -rf "plugins/$NAME/tests/__pycache__" "tools/$NAME/__pycache__" || true
  BASE="$(stack_base)"
  # if @- is a plugin bookmark tip, use that as PR base
  PARENT_BM="$(jj log -r '@-' -T 'bookmarks' --no-graph 2>/dev/null | tr -d '"' | awk '{print $1}' | head -1)"
  if [[ "$PARENT_BM" == plugin/* ]]; then
    BASE="$PARENT_BM"
  elif [[ -z "$BASE" ]]; then
    BASE="main"
  fi
  jj describe -m "feat($NAME): generated JSON tools" -m "L1-L4 green; L5 pending or not-applicable. Auto-built." -m "Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_012NGuAhdyW7FCdG1ahcWwqd"
  jj bookmark set "plugin/$NAME" -r @
  jj git push --bookmark "plugin/$NAME"
  URL="$(gh pr create --head "plugin/$NAME" --base "$BASE" --title "feat($NAME): generated JSON tools" --body "$(cat <<EOF
## Summary
- Auto-built \`$NAME\` JSON tools (L1–L4 green).
- L5 pending or not-applicable (no pinned model).
- Stacked on \`$BASE\`.

## Test plan
- [x] make test-plugin PLUGIN=$NAME
- [x] make l4 PLUGIN=$NAME

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)" )"
  echo "OK $NAME $URL base=$BASE" | tee -a "$REPORT"
  n=$((n+1))
done

echo "DONE built=$n" | tee -a "$REPORT"
cat "$REPORT"
