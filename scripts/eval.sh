#!/usr/bin/env bash
# L5 uplift eval. Record baseline BEFORE treatment.
#
#   ./scripts/eval.sh baseline          # plugins off (required first)
#   ./scripts/eval.sh treatment         # after baseline exists
#   HELD_OUT=1 ./scripts/eval.sh baseline   # held-out tasks (tasks/<suite>/held-out/v<N>/); does not touch default baseline pointers
#   AGENT=ollama OLLAMA_MODEL=... ./scripts/eval.sh baseline
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CONDITION="${1:-baseline}"
AGENT="${AGENT:-stub}"
SUITE="${SUITE:-navigation}"
VERSION="${VERSION:-1}"
SEEDS="${SEEDS:-3}"

COMPARE_DEFAULT=0
if [[ "${HELD_OUT:-0}" != "1" && "$SUITE" == "navigation" ]]; then
  COMPARE_DEFAULT=1
fi

if [[ "$CONDITION" == "treatment" && "$COMPARE_DEFAULT" == "1" ]]; then
  if [[ ! -f "$ROOT/testing/eval/runs/BASELINE_NAVIGATION_V1.json" ]]; then
    echo "error: no baseline at testing/eval/runs/BASELINE_NAVIGATION_V1.json" >&2
    echo "run: ./scripts/eval.sh baseline" >&2
    exit 2
  fi
fi

if [[ "$CONDITION" != "baseline" && "$CONDITION" != "treatment" ]]; then
  echo "usage: $0 baseline|treatment" >&2
  exit 2
fi

EXTRA=()
if [[ "${HELD_OUT:-0}" == "1" ]]; then
  EXTRA+=(--held-out)
fi

python3 "$ROOT/testing/eval/run_eval.py" \
  --suite "$SUITE" \
  --version "$VERSION" \
  --condition "$CONDITION" \
  --agent "$AGENT" \
  --seeds "$SEEDS" \
  ${EXTRA[@]+"${EXTRA[@]}"}

if [[ "$CONDITION" == "treatment" && "$COMPARE_DEFAULT" == "1" && -f "$ROOT/testing/eval/runs/BASELINE_NAVIGATION_V1.json" ]]; then
  echo
  echo "=== Compare vs baseline (§6e gates) ==="
  python3 "$ROOT/testing/eval/compare_eval.py"
fi
