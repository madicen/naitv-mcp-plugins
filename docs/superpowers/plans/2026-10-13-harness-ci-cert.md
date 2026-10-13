# Harness CI, layout dedupe, and L5 cert skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Canonical `plugins/<name>/plugin.json` only, PR + nightly GitHub Actions matching TEST_PLAN cadence, `PERF_RUNNER_ID` on perf reports, and L5 held-out / structure / ablation scaffolding.

**Architecture:** Delete legacy flat manifests and point `registry.json` at directory `plugin.json`. Shared runners already prefer that path; tighten helpers and docs. Add `.github/workflows/pr.yml` (catalog + soft L4) and `nightly.yml` (50k perf + stub eval + ablation). Extend `run_perf.py` / `run_eval.py` with small opt-in flags; add `run_ablation.py` as a thin leave-one-out driver over existing eval.

**Tech Stack:** Python 3.12, pytest, Go (plugin helpers + optional `naitv-mcp` install), GitHub Actions, bash wrappers under `scripts/`.

**Spec:** `docs/superpowers/specs/2026-10-13-harness-ci-cert-design.md`

## Global Constraints

- Version control: **jj only** (`jj commit -m "…"`). No `git commit` for local history. One jj commit per task.
- No naitv-mcp core changes.
- Do not wire held-out into default `./scripts/eval.sh` (opt-in `HELD_OUT=1` only).
- No mandatory Ollama in CI.
- YAGNI: skeleton tasks only (2–3 held-out, 1–2 structure); no full cert suites.
- After delete, old raw URLs `…/plugins/<name>.json` 404 on `main` — note in PR summary.

## File map

| Path | Responsibility |
|------|----------------|
| `plugins/{lazy-dev,loop-engineering-go,structural-anchor,symbol-navigator}.json` | **Delete** (legacy flat) |
| `plugins/*/plugin.json` | Sole installable manifest |
| `registry.json` | URLs → `…/plugins/<name>/plugin.json` |
| `README.md` | Install examples, table links, adding-plugin steps |
| `adapters/*/AGENTS.md` | Source-of-truth path |
| `docs/how-agent-portable-plugins-work.md` | Canonical path note |
| `testing/integration/cross_plugin_check.py` | Directory manifests only |
| `scripts/scaffold_plugin.sh` | Directory-only (no flat copy) |
| `testing/PLUGIN_HARNESS.md` | Layout + CI + held-out notes |
| `testing/perf/run_perf.py` | `runner_id` from `PERF_RUNNER_ID` |
| `testing/perf/HARDWARE.md` | Dedicated runner instructions |
| `testing/perf/tests/test_runner_id.py` | Unit test for runner_id |
| `testing/eval/run_eval.py` | `--held-out` task root |
| `scripts/eval.sh` | Forward `HELD_OUT=1` → `--held-out` |
| `testing/eval/tasks/navigation/held-out/v1/*.json` | Held-out tasks |
| `testing/eval/tasks/structure/{suite.json,v1/*.json}` | Structure suite stub |
| `testing/eval/run_ablation.py` | Leave-one-out driver |
| `testing/eval/tests/test_held_out_path.py` | Path selection test |
| `testing/eval/tests/test_ablation.py` | Ablation smoke |
| `.github/workflows/pr.yml` | Catalog + soft L4 |
| `.github/workflows/nightly.yml` | Perf + stub eval + ablation |
| `TEST_PLAN.md` §8 | Point at workflow files |

---

### Task 1: Layout dedupe (delete flats; registry + docs)

**Files:**
- Delete: `plugins/lazy-dev.json`, `plugins/loop-engineering-go.json`, `plugins/structural-anchor.json`, `plugins/symbol-navigator.json`
- Modify: `registry.json`
- Modify: `README.md`
- Modify: `adapters/lazy-dev/AGENTS.md`, `adapters/structural-anchor/AGENTS.md`, `adapters/symbol-navigator/AGENTS.md`
- Modify: `docs/how-agent-portable-plugins-work.md`
- Modify: `testing/integration/cross_plugin_check.py`
- Modify: `scripts/scaffold_plugin.sh`
- Modify: `testing/PLUGIN_HARNESS.md` (layout section only)

**Interfaces:**
- Consumes: existing `plugins/<name>/plugin.json` for all four plugins
- Produces: registry URLs of the form `https://raw.githubusercontent.com/madicen/naitv-mcp-plugins/main/plugins/<name>/plugin.json`

- [ ] **Step 1: Write failing check that flats must not exist**

Create `testing/integration/test_manifest_layout.py`:

```python
"""Catalog layout: only plugins/<name>/plugin.json (no flat plugins/*.json)."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLUGINS = REPO / "plugins"


def test_no_flat_plugin_json():
    flats = sorted(PLUGINS.glob("*.json"))
    assert flats == [], f"legacy flat manifests still present: {flats}"


def test_every_plugin_dir_has_plugin_json():
    dirs = [p for p in PLUGINS.iterdir() if p.is_dir() and not p.name.startswith(".")]
    assert dirs, "no plugin directories"
    missing = [p.name for p in dirs if not (p / "plugin.json").is_file()]
    assert missing == [], f"missing plugin.json: {missing}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest testing/integration/test_manifest_layout.py::test_no_flat_plugin_json -v`

Expected: FAIL with assertion listing the four flat files.

- [ ] **Step 3: Delete flats and update consumers**

Delete the four flat files.

`registry.json` — every `url` becomes:

```json
"url": "https://raw.githubusercontent.com/madicen/naitv-mcp-plugins/main/plugins/<name>/plugin.json"
```

for `loop-engineering-go`, `lazy-dev`, `structural-anchor`, `symbol-navigator`.

`README.md` replacements (exact intent):

- Install URL example → `…/plugins/loop-engineering-go/plugin.json`
- Local path example → `…/plugins/my-plugin/plugin.json` or `…/plugin.json`
- Table links → `plugins/<name>/plugin.json`
- “Adding a plugin” step 1 → create `plugins/<your-plugin-name>/plugin.json` (prefer `./scripts/scaffold_plugin.sh <name>`)
- Example registry `url` → `…/plugins/your-plugin-name/plugin.json`
- Drop or rewrite “no CI gate” line (CI arrives in Task 6; for now say catalog is validated by `./scripts/test_all.sh`)

Adapters — change the HTML comment path only:

- `plugins/lazy-dev.json` → `plugins/lazy-dev/plugin.json`
- `plugins/structural-anchor.json` → `plugins/structural-anchor/plugin.json`
- `plugins/symbol-navigator.json` → `plugins/symbol-navigator/plugin.json`

`docs/how-agent-portable-plugins-work.md` — replace `plugins/lazy-dev.json` with `plugins/lazy-dev/plugin.json` (both prose mentions).

`cross_plugin_check.py` — directory only:

```python
def load_manifests() -> list[tuple[str, dict]]:
    """Load plugins/<name>/plugin.json only."""
    out: list[tuple[str, dict]] = []
    for path in sorted(PLUGINS.glob("*/plugin.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        out.append((str(path.relative_to(REPO)), data))
    return out
```

`scaffold_plugin.sh` — remove the “copy legacy flat” branch; always write a stub `plugin.json` (keep harness + test_manifest as today). Update the header comment to say directory-only.

`PLUGIN_HARNESS.md` layout section — replace “preferred / legacy” with:

```markdown
plugins/<name>/
  plugin.json          # sole installable manifest (registry + install_plugin URL)
  harness.json         # optional test profile
  tests/
```

Remove the paragraph that says legacy flat still loads for install.

- [ ] **Step 4: Run layout tests + catalog smoke**

Run:

```bash
python3 -m pytest testing/integration/test_manifest_layout.py -v
python3 testing/integration/cross_plugin_check.py
./scripts/test_all.sh
```

Expected: all pass; `test_all` reports all 4 plugins passed.

- [ ] **Step 5: Commit**

```bash
jj commit -m "$(cat <<'EOF'
refactor(plugins): drop flat manifests; registry uses plugin.json

Canonical install path is plugins/<name>/plugin.json only.
EOF
)"
```

---

### Task 2: Perf `runner_id` + HARDWARE.md

**Files:**
- Modify: `testing/perf/run_perf.py`
- Create: `testing/perf/HARDWARE.md`
- Create: `testing/perf/tests/test_runner_id.py`

**Interfaces:**
- Consumes: env `PERF_RUNNER_ID` (optional string)
- Produces: report field `runner_id: str | None` next to `hardware`

- [ ] **Step 1: Write failing test**

```python
# testing/perf/tests/test_runner_id.py
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_perf as rp


def test_runner_id_reads_env(monkeypatch):
    monkeypatch.setenv("PERF_RUNNER_ID", "ci-nightly-box-1")
    assert rp.runner_id() == "ci-nightly-box-1"


def test_runner_id_none_when_unset(monkeypatch):
    monkeypatch.delenv("PERF_RUNNER_ID", raising=False)
    assert rp.runner_id() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest testing/perf/tests/test_runner_id.py -v`

Expected: FAIL (`runner_id` not defined).

- [ ] **Step 3: Implement**

In `testing/perf/run_perf.py`, after `SLACK = 0.10`:

```python
def runner_id() -> str | None:
    return os.environ.get("PERF_RUNNER_ID") or None
```

In the `report = {…}` dict (around the existing `"hardware": hardware_info()` line), add:

```python
"runner_id": runner_id(),
```

Create `testing/perf/HARDWARE.md`:

```markdown
# Perf hardware identity

Release-gate L3 numbers must come from a **fixed runner**, not a laptop.

## Required env

| Variable | Purpose |
|---|---|
| `PERF_RUNNER_ID` | Stable label written into every perf JSON report (e.g. `nightly-m2-mini`) |
| `PERF_RUNS_ON` (GitHub Actions repo variable) | Optional `runs-on` override for `.github/workflows/nightly.yml` (self-hosted label or larger runner) |

Laptop / ad-hoc results without `PERF_RUNNER_ID` are fine for local iteration but **inadmissible** for certification or release gates.

## Nightly

The nightly workflow sets `PERF_RUNNER_ID` from `vars.PERF_RUNNER_ID` when present, otherwise `runner-${{ runner.name }}`. Point a self-hosted runner at the repo and set `PERF_RUNS_ON` / `PERF_RUNNER_ID` in repository variables when ready.
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest testing/perf/tests/test_runner_id.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
jj commit -m "$(cat <<'EOF'
test(perf): record PERF_RUNNER_ID on L3 reports

Laptop results without a runner id stay local-only for release gates.
EOF
)"
```

---

### Task 3: Held-out task path (`--held-out` / `HELD_OUT=1`)

**Files:**
- Modify: `testing/eval/run_eval.py`
- Modify: `scripts/eval.sh`
- Create: `testing/eval/tasks/navigation/held-out/v1/ho-001-where-is-add.json`
- Create: `testing/eval/tasks/navigation/held-out/v1/ho-002-search-greet.json`
- Create: `testing/eval/tasks/navigation/held-out/v1/ho-003-go-package.json`
- Create: `testing/eval/tests/test_held_out_path.py`

**Interfaces:**
- Consumes: `load_tasks(suite, version, *, held_out: bool = False)`
- Produces: task root `tasks/<suite>/held-out/v<version>/` when `held_out` else `tasks/<suite>/v<version>/`
- CLI: `run_eval.py --held-out`; `HELD_OUT=1 ./scripts/eval.sh …` appends `--held-out`

- [ ] **Step 1: Write failing test**

```python
# testing/eval/tests/test_held_out_path.py
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_eval import task_dir


def test_task_dir_default():
    p = task_dir("navigation", 1, held_out=False)
    assert p.as_posix().endswith("tasks/navigation/v1")


def test_task_dir_held_out():
    p = task_dir("navigation", 1, held_out=True)
    assert p.as_posix().endswith("tasks/navigation/held-out/v1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest testing/eval/tests/test_held_out_path.py -v`

Expected: FAIL (`task_dir` missing).

- [ ] **Step 3: Implement path helper + CLI + shell + tasks**

In `run_eval.py`, replace `load_tasks` with:

```python
def task_dir(suite: str, version: int, *, held_out: bool = False) -> Path:
    if held_out:
        return TASKS_ROOT / suite / "held-out" / f"v{version}"
    return TASKS_ROOT / suite / f"v{version}"


def load_tasks(suite: str, version: int, *, held_out: bool = False) -> list[dict[str, Any]]:
    directory = task_dir(suite, version, held_out=held_out)
    if not directory.is_dir():
        raise SystemExit(f"missing task suite: {directory}")
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.json"))
    ]
```

Add argparse flag:

```python
parser.add_argument(
    "--held-out",
    action="store_true",
    help="load tasks/<suite>/held-out/v<version>/ instead of tasks/<suite>/v<version>/",
)
```

Call site:

```python
tasks = load_tasks(args.suite, args.version, held_out=args.held_out)
```

When writing reports under held-out, include `"held_out": args.held_out` in the report dict. **Do not** overwrite `baselines/navigation-v1-baseline.json` or `BASELINE_NAVIGATION_V1.json` when `held_out` is true — skip those pointer writes (only write the stamped `out_dir` + a held-out-specific latest name):

```python
latest_name = (
    f"{args.suite}-v{args.version}-heldout-{args.condition}-latest.json"
    if args.held_out
    else f"{args.suite}-v{args.version}-{args.condition}-latest.json"
)
latest = RUNS_ROOT / latest_name
```

And wrap the baseline/treatment pointer block:

```python
if args.condition == "baseline" and not args.held_out:
    ...  # existing pointer writes
if args.condition == "treatment" and not args.held_out:
    ...  # existing treatment pointer
```

`scripts/eval.sh` — after building the python args, before the python invocation:

```bash
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
  "${EXTRA[@]}"
```

Update the header comment to document `HELD_OUT=1 ./scripts/eval.sh baseline`.

Held-out tasks (new IDs — must not reuse `nav-00*` ids):

`ho-001-where-is-add.json`:

```json
{
  "id": "ho-001-where-is-add",
  "suite": "navigation",
  "version": 1,
  "category": "navigation",
  "difficulty": "easy",
  "fixture": "py-small",
  "request": "Where is the add function defined? Give file path and kind.",
  "success": {
    "type": "answer_contains_all",
    "values": ["add", "greeter.py", "function"]
  },
  "control": false
}
```

`ho-002-search-greet.json`:

```json
{
  "id": "ho-002-search-greet",
  "suite": "navigation",
  "version": 1,
  "category": "navigation",
  "difficulty": "easy",
  "fixture": "py-small",
  "request": "Which symbols match the pattern greet? List at least one name.",
  "success": {
    "type": "answer_contains_all",
    "values": ["Greet"]
  },
  "control": false
}
```

`ho-003-go-package.json`:

```json
{
  "id": "ho-003-go-package",
  "suite": "navigation",
  "version": 1,
  "category": "structure",
  "difficulty": "easy",
  "fixture": "go-small",
  "request": "Name one Go package under this root and one exported symbol from it.",
  "success": {
    "type": "answer_contains_all",
    "values": ["greeter"]
  },
  "control": false
}
```

- [ ] **Step 4: Verify**

```bash
python3 -m pytest testing/eval/tests/test_held_out_path.py -v
# default path unchanged:
python3 -c "from pathlib import Path; import sys; sys.path.insert(0,'testing/eval'); from run_eval import task_dir; assert 'held-out' not in task_dir('navigation',1).as_posix()"
HELD_OUT=1 SEEDS=1 ./scripts/eval.sh baseline
```

Expected: pytest PASS; baseline held-out run writes under `testing/eval/runs/navigation-v1-heldout-…` and does **not** clobber `BASELINE_NAVIGATION_V1.json` mtime for the default suite (spot-check: held-out report has `"held_out": true`).

- [ ] **Step 5: Commit**

```bash
jj commit -m "$(cat <<'EOF'
feat(eval): add held-out navigation tasks behind --held-out

Default eval.sh path stays on tasks/navigation/v1.
EOF
)"
```

---

### Task 4: Structure suite stub

**Files:**
- Create: `testing/eval/tasks/structure/suite.json`
- Create: `testing/eval/tasks/structure/v1/str-001-list-packages.json`
- Create: `testing/eval/tasks/structure/v1/str-002-primary-language.json`

**Interfaces:**
- Consumes: existing `run_eval.py --suite structure` (no code change if `suite.json` + `v1/` exist)
- Produces: `treatment_plugins: ["structural-anchor"]`

- [ ] **Step 1: Add suite metadata + tasks**

`suite.json`:

```json
{
  "name": "structure",
  "description": "Orientation / package-map uplift (structural-anchor)",
  "treatment_plugins": ["structural-anchor"]
}
```

`str-001-list-packages.json`:

```json
{
  "id": "str-001-list-packages",
  "suite": "structure",
  "version": 1,
  "category": "structure",
  "difficulty": "easy",
  "fixture": "go-small",
  "request": "List the top-level Go packages visible under this root.",
  "success": {
    "type": "answer_contains_all",
    "values": ["greeter"]
  },
  "control": false
}
```

`str-002-primary-language.json`:

```json
{
  "id": "str-002-primary-language",
  "suite": "structure",
  "version": 1,
  "category": "structure",
  "difficulty": "easy",
  "fixture": "py-small",
  "request": "What is the primary language of this small project?",
  "success": {
    "type": "answer_contains_all",
    "values": ["Python"]
  },
  "control": false
}
```

- [ ] **Step 2: Smoke baseline (no MCP required)**

Run: `SUITE=structure SEEDS=1 ./scripts/eval.sh baseline`

Expected: exit 0; writes `testing/eval/runs/structure-v1-baseline-…/report.json`. (Baseline pointer files are navigation-specific today — that is OK; structure only needs the stamped report.)

- [ ] **Step 3: Commit**

```bash
jj commit -m "$(cat <<'EOF'
feat(eval): add structure suite stub for L5 skeleton

Two orientation tasks; treatment_plugins = structural-anchor.
EOF
)"
```

---

### Task 5: Leave-one-out ablation (`run_ablation.py`)

**Files:**
- Create: `testing/eval/run_ablation.py`
- Create: `testing/eval/tests/test_ablation.py`
- Modify: `testing/PLUGIN_HARNESS.md` (ablation + held-out one-liners)

**Interfaces:**
- Consumes: `treatment_plugins_for(suite)`, `run_eval` helpers / subprocess to `run_eval.py`, or in-process loop calling the same MCP path
- Produces: `testing/eval/runs/ablation-<suite>-v<version>-<stamp>/report.json` with per-dropped-plugin summaries
- CLI: `python testing/eval/run_ablation.py --suite navigation --seeds 1`

Lazy approach: subprocess `run_eval.py` is heavy (full MCP each time). Prefer **in-process**: import `treatment_plugins_for`, `load_tasks`, `run_task`, `summarize`, `mcp_session` from `run_eval` / existing modules and for each dropped plugin run treatment with the remaining list.

- [ ] **Step 1: Write failing test**

```python
# testing/eval/tests/test_ablation.py
from __future__ import annotations

from testing.eval.run_ablation import leave_one_out_sets


def test_leave_one_out_sets():
    full = ["structural-anchor", "symbol-navigator"]
    sets = leave_one_out_sets(full)
    assert sets == [
        ("structural-anchor", ["symbol-navigator"]),
        ("symbol-navigator", ["structural-anchor"]),
    ]
```

If import path is awkward under pytest, use `sys.path` insert like other eval tests:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_ablation import leave_one_out_sets
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest testing/eval/tests/test_ablation.py -v`

Expected: FAIL (module missing).

- [ ] **Step 3: Implement `run_ablation.py`**

```python
#!/usr/bin/env python3
"""Leave-one-out ablation over suite treatment_plugins (stub agent)."""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVAL_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_ROOT))

from mcp_session import mcp_session  # noqa: E402
from run_eval import (  # noqa: E402
    load_tasks,
    run_task,
    summarize,
    treatment_plugins_for,
)

RUNS_ROOT = EVAL_ROOT / "runs"


def leave_one_out_sets(plugins: list[str]) -> list[tuple[str, list[str]]]:
    """Return (dropped, remaining) for each plugin in the full treatment set."""
    return [(p, [x for x in plugins if x != p]) for p in plugins]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="navigation")
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--seed-base", type=int, default=42)
    parser.add_argument("--agent", choices=("stub",), default="stub")
    args = parser.parse_args()

    if shutil.which("naitv-mcp") is None:
        print("warn: naitv-mcp not on PATH; ablation skipped", file=sys.stderr)
        return 0

    full = treatment_plugins_for(args.suite)
    if len(full) < 2:
        print(f"warn: need ≥2 treatment plugins for ablation; got {full}", file=sys.stderr)
        return 0

    tasks = load_tasks(args.suite, args.version, held_out=False)
    arms: list[dict[str, Any]] = []

    for dropped, remaining in leave_one_out_sets(full):
        results: list[dict[str, Any]] = []
        with mcp_session(plugins=remaining) as client:
            order = list(tasks)
            random.Random(args.seed_base).shuffle(order)
            for task in order:
                for i in range(args.seeds):
                    results.append(
                        run_task(
                            task,
                            condition="treatment",
                            agent=args.agent,
                            seed=args.seed_base + i,
                            client=client,
                            plugins=remaining,
                        )
                    )
        arms.append(
            {
                "dropped": dropped,
                "plugins": remaining,
                "summary": summarize(results),
                "n_results": len(results),
            }
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = RUNS_ROOT / f"ablation-{args.suite}-v{args.version}-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "kind": "ablation",
        "suite": args.suite,
        "suite_version": args.version,
        "full_plugins": full,
        "agent": args.agent,
        "seeds": args.seeds,
        "arms": arms,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "runner_id": os.environ.get("PERF_RUNNER_ID"),
    }
    path = out_dir / "report.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    latest = RUNS_ROOT / f"ablation-{args.suite}-v{args.version}-latest.json"
    latest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"arms": [{"dropped": a["dropped"], "summary": a["summary"]} for a in arms]}, indent=2))
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Document in `PLUGIN_HARNESS.md` (short):

```markdown
## L5 extras

- Held-out: `HELD_OUT=1 ./scripts/eval.sh baseline` (never default).
- Ablation: `python3 testing/eval/run_ablation.py --suite navigation --seeds 1`
- Structure suite: `SUITE=structure ./scripts/eval.sh baseline`
```

- [ ] **Step 4: Unit test + optional live smoke**

```bash
python3 -m pytest testing/eval/tests/test_ablation.py -v
# if naitv-mcp on PATH:
python3 testing/eval/run_ablation.py --suite navigation --seeds 1
```

Expected: unit test PASS; live smoke writes ablation report or exits 0 with warn if no binary.

- [ ] **Step 5: Commit**

```bash
jj commit -m "$(cat <<'EOF'
feat(eval): leave-one-out ablation runner for treatment plugins

Stub-agent arms drop one plugin at a time and write ablation reports.
EOF
)"
```

---

### Task 6: PR workflow (`.github/workflows/pr.yml`)

**Files:**
- Create: `.github/workflows/pr.yml`
- Modify: `TEST_PLAN.md` §8 (add workflow file pointers; keep table)
- Modify: `README.md` — one line that PRs run `./scripts/test_all.sh` via Actions (optional badge skip)

**Interfaces:**
- Consumes: `./scripts/test_all.sh`, `./scripts/l4.sh`, Go modules under `tools/*/go_*`
- Produces: required `catalog` job; soft `l4` job

- [ ] **Step 1: Add workflow file**

Create `.github/workflows/pr.yml`:

```yaml
name: pr

on:
  pull_request:
  push:
    branches: [main, "test/**"]

jobs:
  catalog:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: actions/setup-go@v5
        with:
          go-version: "stable"
      - name: Python deps
        run: |
          python -m venv .venv
          . .venv/bin/activate
          pip install pytest pytest-cov
      - name: Catalog L1–L3
        run: |
          . .venv/bin/activate
          ./scripts/test_all.sh
      - name: Go helpers
        run: |
          go test ./tools/structural-anchor/go_symbols/...
          go test ./tools/symbol-navigator/go_nav/...

  l4:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: actions/setup-go@v5
        with:
          go-version: "stable"
      - name: Soft L4 via naitv-mcp
        # Install from public module. If install fails or binary missing, exit 0.
        # If binary is present, L4 failures fail the job.
        run: |
          set -euo pipefail
          go install github.com/madicen/naitv-mcp/cmd/naitv-mcp@latest || {
            echo "warn: go install naitv-mcp failed; skipping L4"
            exit 0
          }
          export PATH="$(go env GOPATH)/bin:$PATH"
          if ! command -v naitv-mcp >/dev/null 2>&1; then
            echo "warn: naitv-mcp not on PATH after install; skipping L4"
            exit 0
          fi
          python -m venv .venv
          . .venv/bin/activate
          pip install pytest pytest-cov
          RUN_L4=1 ./scripts/l4.sh structural-anchor
          RUN_L4=1 ./scripts/l4.sh symbol-navigator
```

Note: `./scripts/l4.sh` already errors if binary missing; the wrapper above only reaches it when install succeeded.

- [ ] **Step 2: Update TEST_PLAN §8**

After the cadence table in §8, add:

```markdown
Workflows (this repo):

| File | Cadence |
|---|---|
| `.github/workflows/pr.yml` | Every PR / push to `main` and `test/**` — catalog `test_all` + Go helper tests; soft L4 |
| `.github/workflows/nightly.yml` | Cron `0 6 * * *` UTC + `workflow_dispatch` — 50k perf + stub L5 + ablation |
```

- [ ] **Step 3: Local YAML sanity**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/pr.yml'))"`  
If PyYAML missing: `python3 -c "from pathlib import Path; t=Path('.github/workflows/pr.yml').read_text(); assert 'catalog:' in t and 'test_all' in t"`

Expected: no exception.

- [ ] **Step 4: Commit**

```bash
jj commit -m "$(cat <<'EOF'
ci: add PR workflow for catalog test_all and soft L4

Go helper tests run on every PR; L4 skips cleanly if naitv-mcp install fails.
EOF
)"
```

---

### Task 7: Nightly workflow + docs closeout

**Files:**
- Create: `.github/workflows/nightly.yml`
- Modify: `testing/PLUGIN_HARNESS.md` (CI commands section if not already covered)
- Modify: `README.md` “Adding a plugin” CI sentence if still stale

**Interfaces:**
- Consumes: `scripts/perf.sh`, `scripts/eval.sh`, `testing/eval/run_ablation.py`, repo vars `PERF_RUNS_ON`, `PERF_RUNNER_ID`
- Produces: artifacts for perf latest JSON + eval runs

- [ ] **Step 1: Add nightly.yml**

```yaml
name: nightly

on:
  schedule:
    - cron: "0 6 * * *"
  workflow_dispatch:

jobs:
  perf:
    runs-on: ${{ vars.PERF_RUNS_ON != '' && vars.PERF_RUNS_ON || 'ubuntu-latest' }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: actions/setup-go@v5
        with:
          go-version: "stable"
      - name: Python deps
        run: |
          python -m venv .venv
          . .venv/bin/activate
          pip install pytest pytest-cov
      - name: Perf 50k
        env:
          PERF_RUNNER_ID: ${{ vars.PERF_RUNNER_ID != '' && vars.PERF_RUNNER_ID || format('runner-{0}', runner.name) }}
        run: |
          . .venv/bin/activate
          ./scripts/perf.sh structural-anchor
          ./scripts/perf.sh symbol-navigator
      - uses: actions/upload-artifact@v4
        with:
          name: perf-latest
          path: testing/perf/results/*-latest.json

  eval-stub:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: actions/setup-go@v5
        with:
          go-version: "stable"
      - name: Soft install naitv-mcp
        run: |
          set -euo pipefail
          go install github.com/madicen/naitv-mcp/cmd/naitv-mcp@latest || true
          echo "$(go env GOPATH)/bin" >> "$GITHUB_PATH"
      - name: Stub L5 + ablation
        run: |
          set -euo pipefail
          python -m venv .venv
          . .venv/bin/activate
          pip install pytest pytest-cov
          if ! command -v naitv-mcp >/dev/null 2>&1; then
            echo "warn: naitv-mcp missing; running baseline only"
            SEEDS=1 ./scripts/eval.sh baseline
            exit 0
          fi
          SEEDS=1 ./scripts/eval.sh baseline
          SEEDS=1 ./scripts/eval.sh treatment
          python3 testing/eval/run_ablation.py --suite navigation --seeds 1
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: eval-runs
          path: |
            testing/eval/runs/*-latest.json
            testing/eval/runs/ablation-*-latest.json
```

- [ ] **Step 2: PLUGIN_HARNESS CI blurb**

Append if missing:

```markdown
## CI

- PR: `.github/workflows/pr.yml` → `./scripts/test_all.sh` + Go helper tests; soft L4.
- Nightly: `.github/workflows/nightly.yml` → `./scripts/perf.sh` (50k) + stub eval + ablation.
- Install URLs in `registry.json` point at `plugins/<name>/plugin.json`.
```

- [ ] **Step 3: Sanity**

```bash
python3 -c "from pathlib import Path; t=Path('.github/workflows/nightly.yml').read_text(); assert 'perf.sh' in t and 'run_ablation' in t and '0 6' in t"
# final catalog gate
./scripts/test_all.sh
python3 -m pytest testing/integration/test_manifest_layout.py testing/perf/tests/test_runner_id.py testing/eval/tests/test_held_out_path.py testing/eval/tests/test_ablation.py -v
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
jj commit -m "$(cat <<'EOF'
ci: add nightly perf and stub L5 ablation workflow

Uses PERF_RUNNER_ID / PERF_RUNS_ON repo vars when set.
EOF
)"
```

---

## Spec coverage checklist

| Spec requirement | Task |
|---|---|
| Delete flat manifests; registry → `plugin.json` | 1 |
| README / adapters / scaffold / cross_plugin / PLUGIN_HARNESS layout | 1 |
| PR workflow catalog + soft L4 | 6 |
| Nightly 50k + stub eval + ablation | 7 |
| `PERF_RUNNER_ID` + HARDWARE.md | 2 |
| Held-out tasks + `--held-out` / `HELD_OUT=1` | 3 |
| Structure suite stub | 4 |
| `run_ablation.py` leave-one-out | 5 |
| TEST_PLAN §8 workflow pointers | 6 |
| No default held-out contamination | 3 (pointer skip + opt-in only) |
| No Ollama CI gate | 6–7 (not present) |

## Plan self-review

1. **Spec coverage:** All success criteria map to tasks 1–7; URL break called out in Global Constraints / PR note.
2. **Placeholders:** None; workflow YAML and task JSON inlined.
3. **Type consistency:** `task_dir` / `load_tasks(..., held_out=)` / `leave_one_out_sets` / `runner_id()` names match across tasks.
