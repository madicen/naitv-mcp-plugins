# Harness CI, layout dedupe, and L5 certification skeleton

**Date:** 2026-10-13  
**Status:** Approved for planning  
**Repo:** naitv-mcp-plugins  

## Problem

The L1–L5 harness works locally for the current catalog, but:

1. Plugin manifests are duplicated (`plugins/<name>.json` and `plugins/<name>/plugin.json`).
2. There is no GitHub Actions cadence matching TEST_PLAN.
3. Full 50k perf is smoke-only; no locked nightly runner story.
4. L5 lacks held-out / structure / ablation scaffolding for certification.

## Goals

- Single canonical manifest path: `plugins/<name>/plugin.json`.
- PR CI: L1–L3 (+ L4 when possible); nightly: 50k perf + stub L5.
- Perf reports identify the runner (`PERF_RUNNER_ID`).
- L5 skeleton: held-out navigation tasks, structure suite stub, leave-one-out ablation.
- No naitv-mcp core changes.

## Non-goals

- Full 40/120-task certification suites.
- Mandatory Ollama in CI (optional / manual only).
- Text-mode L2/L4 for loop-engineering-go tools.
- Changing install semantics inside naitv-mcp beyond registry URL paths.

## Design

### 1. Layout dedupe (choice A)

| Before | After |
|---|---|
| `plugins/<name>.json` + `plugins/<name>/plugin.json` | `plugins/<name>/plugin.json` only |

Actions:

- Delete flat `plugins/{lazy-dev,loop-engineering-go,structural-anchor,symbol-navigator}.json`.
- Point `registry.json` `url` fields at  
  `https://raw.githubusercontent.com/madicen/naitv-mcp-plugins/main/plugins/<name>/plugin.json`.
- Update README install examples, plugin table links, “Adding a plugin” steps.
- Update adapter pointers: `adapters/{lazy-dev,structural-anchor,symbol-navigator}/AGENTS.md` (and any loop-engineering adapter) to cite `plugins/<name>/plugin.json`.
- `testing/integration/cross_plugin_check.py`: prefer directory manifests; do not require flat files.
- `scripts/scaffold_plugin.sh`: stop emitting legacy flat JSON; directory-only layout.
- `testing/PLUGIN_HARNESS.md`: note that install URLs use `plugin.json`.

**Compatibility note:** Existing bookmarks / docs that link the old raw URL will 404 after merge to `main`. Locally installed plugins that cached the old `source` URL keep working until reinstall/update; call this out in the PR summary.

### 2. CI workflows

No workflows exist yet; add both files under `.github/workflows/`.

#### PR / push — `.github/workflows/pr.yml`

Triggers: `pull_request`, `push` to `main` and `test/**`.

Jobs:

1. **catalog** (ubuntu-latest) — required green
   - Checkout; set up Python 3.12 + Go (stable).
   - `python -m venv .venv && pip install pytest pytest-cov`
   - `./scripts/test_all.sh` (L1–L3 per harness layers).
   - `go test` in `tools/structural-anchor/go_symbols` and `tools/symbol-navigator/go_nav`.
2. **l4** (ubuntu-latest) — soft
   - Attempt `go install` of `naitv-mcp` from its public module (path documented in workflow comments).
   - If `naitv-mcp` is on `PATH`: `RUN_L4=1 ./scripts/l4.sh structural-anchor` and `symbol-navigator`.
   - If install or binary missing: print a warning and **exit 0** (do not fail the PR). Failures after a successful install still fail the job so L4 regressions are visible when L4 actually runs.

#### Nightly — `.github/workflows/nightly.yml`

Triggers: `schedule` (`0 6 * * *` UTC) + `workflow_dispatch`.

Jobs:

1. **perf**
   - `runs-on`: repository variable `PERF_RUNS_ON` if set, else `ubuntu-latest`.
   - `./scripts/perf.sh structural-anchor` and `./scripts/perf.sh symbol-navigator` (default 50k).
   - Upload `testing/perf/results/*-latest.json` as artifacts.
2. **eval-stub**
   - `SEEDS=1 ./scripts/eval.sh baseline` then `treatment` (default navigation suite).
   - `python testing/eval/run_ablation.py --suite navigation --seeds 1`.
   - Upload eval reports under `testing/eval/runs/` (gitignored; artifacts only).

Ollama: out of scope for green CI. Document `AGENT=ollama` for local runs; optional `workflow_dispatch` input can be added later without blocking this work.

### 3. Perf hardware identity

- Add `testing/perf/HARDWARE.md`: how to set a dedicated runner, expected `PERF_RUNNER_ID`, and that laptop results are inadmissible for release gates.
- Extend `testing/perf/run_perf.py` report with `runner_id: os.environ.get("PERF_RUNNER_ID")`.
- Nightly sets `PERF_RUNNER_ID` from `vars.PERF_RUNNER_ID` or hostname.

### 4. L5 certification skeleton

| Asset | Purpose |
|---|---|
| `testing/eval/tasks/navigation/held-out/v1/*.json` | 2–3 tasks; never used by default stub day-to-day path |
| `testing/eval/tasks/structure/v1/*.json` + `suite.json` | 1–2 orient/structure tasks; treatment_plugins = structural-anchor (+ SN if useful) |
| `testing/eval/run_ablation.py` | Leave-one-out over suite `treatment_plugins`; stub agent; writes ablation report |
| `scripts/eval.sh` | Document held-out; forward `--held-out` when `HELD_OUT=1` |

Default `./scripts/eval.sh` remains `suite=navigation` version `1` (dev tree `tasks/navigation/v1/`). Held-out is opt-in only:

```bash
HELD_OUT=1 ./scripts/eval.sh baseline
# → run_eval.py ... --held-out  (loads tasks/navigation/held-out/v1/)
```

Implementation: `run_eval.py` gains `--held-out`; when set, task root is `tasks/<suite>/held-out/v<version>/` instead of `tasks/<suite>/v<version>/`. Do not change default CLI behavior.

Refresh `testing/eval/baselines/navigation-v1-baseline.json` only if the default v1 task set changes. Held-out may ship without a committed baseline until the first intentional calibration run.

### 5. Docs touch list

- `README.md` — layout, registry URLs, install examples (CI badge optional).
- `adapters/*/AGENTS.md` — source-of-truth path.
- `testing/PLUGIN_HARNESS.md` — CI commands, held-out note.
- `TEST_PLAN.md` §8 — point at `pr.yml` / `nightly.yml` (short).
- `testing/perf/HARDWARE.md` — new.

## Success criteria

- [ ] Zero files matching `plugins/*.json` (only `plugins/<name>/plugin.json`).
- [ ] `registry.json` URLs end in `/plugins/<name>/plugin.json`.
- [ ] `.github/workflows/pr.yml` and `nightly.yml` exist as specified.
- [ ] Ablation script runs leave-one-out for navigation treatment plugins (stub agent).
- [ ] Held-out navigation and structure task dirs exist with ≥1 task each.
- [ ] Perf JSON reports include `runner_id` when `PERF_RUNNER_ID` is set.

## Risks

- **URL break:** consumers of old raw URLs need the PR note / registry bump.
- **L4 flaky in CI:** keep optional until naitv-mcp install is reliable.
- **50k on ubuntu-latest:** may be slow/noisy; `PERF_RUNS_ON` escape hatch required.
- **Held-out contamination:** do not wire held-out into default `eval.sh` or stub day-to-day loops.

## Approval

Design approved 2026-10-13 (dedupe option A; CI option 2; perf option 2; L5 skeleton option 2).

## Spec self-review (2026-10-13)

| Check | Result |
|---|---|
| Placeholders / TBD | None remaining; L4 soft-fail and held-out flag resolved. |
| Consistency | Registry, README, adapters, scaffold, and cross_plugin_check all list the same canonical path. |
| Ambiguity | L4: warn+exit 0 if missing binary; fail if L4 runs and fails. Held-out: `--held-out` / `HELD_OUT=1` only. |
| Scope | Matches approved four items; no Ollama CI gate; no full cert suites. |
| Gaps closed | Explicit “no workflows yet”; adapter AGENTS.md in touch list; old `source` URL reinstall note. |
