# Plugin testing: per-plugin requirements and uplift proof

Status: current. Supersedes `archive/TEST_PLAN_superseded.md`.

Authority split:
- `testing/PLUGIN_HARNESS.md` defines how the shared runners work and the `harness.json` schema. It wins on mechanics.
- This document defines what each plugin must provide, and how we prove a plugin helps a small local model. It wins on requirements.

## 1. Layers

| Layer | Proves | Runner | Blocks |
|---|---|---|---|
| L1 unit | internal logic | `plugins/<name>/tests/` via `scripts/test.sh` | merge |
| L2 contract | JSON I/O contract (one line in, one line out, exit codes, timeout, size, determinism) | `testing/contract/run_contract.py` | merge |
| L3 golden + perf | stable output, latency targets | `testing/golden/`, `testing/perf/` | merge (perf: nightly) |
| L4 integration | entries route through real naitv-mcp | `testing/integration/run_l4.py` (`make l4 PLUGIN=<name>`) | merge (soft in PR CI today) |
| L5 uplift | the plugin makes a small local model better at real tasks | `testing/eval/run_eval.py` | "measured" status |

L1 to L4 say the plugin is correct. Only L5 says it is useful. A plugin with green L1 to L4 and no L5 result is **Verified**, not **helpful**.

## 2. Per-plugin requirements (checklist)

Every plugin, including rules-only ones, must have the items that apply to its profile. The build cycle checks these before it marks a plugin `exists`.

1. `plugins/<name>/plugin.json` validates. Tool names are unique across the whole catalog (`testing/integration/cross_plugin_check.py`).
2. `plugins/<name>/harness.json` declares `profile`, `layers`, and (for JSON tools) `coverage.fail_under: 80`.
3. L1: `plugins/<name>/tests/test_unit.py` (or `_test.go`, bats) with at least one test per tool and one error-path test per tool. No network. Temp dirs only.
4. L2: `testing/contract/schemas/<tool>.schema.json` for every tool, keyed by tool name. Inputs under `testing/fixtures/inputs/<tool>/` including the negatives: malformed JSON, missing required field, nonexistent `root_path`, `..` traversal, and an input over 1 MB.
5. L3 golden: `testing/golden/<plugin>/<tool>/<fixture>.json` for at least three shared fixtures. Golden updates are explicit (`--update-golden`) and reviewed in the PR.
6. L3 perf (only if the tool is on a hot path): targets in `harness.json` → `perf.targets_seconds`. Cold, warm, and cold-start are reported separately.
7. L4: `harness.json` → `l4` with smoke args, `expect_keys`, an invalid-args case, and a post-timeout check.
8. L5 tasks (only for plugins with an `eval_category`): at least 10 dev tasks, each declaring `plugins_expected: ["<name>"]`, placed under `testing/eval/tasks/<category>/`. Include at least 2 control tasks, where the plugin should not change the outcome. The build cycle does not author or read held-out tasks. A human owns those.
9. Rules-only plugins: L1 structural checks on entries (names, delivery, no duplicate tool names). L2 to L4 are skipped automatically.

Fixtures are shared. Reuse `py-small`, `go-small`, `mixed-polyglot`, `empty`, or `hostile` before adding a new one, and justify any new one in the PR.

## 3. Proving a plugin helps a small local model (L5)

This is the part that makes a plugin "useful" rather than "present." The question for each plugin P:

> On tasks P is meant to help with, does a small local model succeed more often with P enabled, without getting worse on tasks P should not affect?

### 3.1 Arms

| Arm | Plugins exposed through naitv-mcp | Everything else |
|---|---|---|
| Baseline (B) | core tools only | identical |
| Treatment (T) | core + P only | identical |

Run both arms on P's tagged tasks and on the control tasks. Comparing P alone (rather than the full set) isolates its effect. Full-set interaction is checked at phase exit (section 3.6).

### 3.2 Agent and model

- The agent must be `AGENT=ollama` with a model pinned in `harness.json` → `l5.model` (name, quantization, context size, temperature, seed). The Makefile defaults to `AGENT=stub`. The stub is a wiring check. **Stub results are never evidence of uplift.**
- If no model is pinned or the runtime is unreachable, record `l5: "pending"` for the plugin. Do not substitute a different model or the stub.
- Seeds: 3 per task per arm (`SEEDS=3`).

### 3.3 Pre-registered gate

Write the gate into `harness.json` → `l5.gate` **before** the first eval run. The cycle may not change it after seeing results.

```json
"l5": {
  "treatment_plugins": ["<name>"],
  "tool_names": ["<tool>"],
  "gate": {
    "min_success_delta_pp": 10,
    "ci_must_exclude_zero": true,
    "max_control_regression_pp": 2,
    "max_nonexistent_symbol_rate_increase": 0,
    "max_tool_call_inflation_pct": 25
  }
}
```

Metrics come from `testing/eval/graders/` (deterministic: tests pass or fail, file scope, symbol existence against the fixture symbol table). No LLM judge is used for certification.

### 3.4 Outcomes

| Result | `l5` value | Meaning |
|---|---|---|
| Gate passes | `measured-helpful` | Measured to help on P's targeted tasks, no control regression. |
| Gate fails | `measured-no-uplift` | Not shown to help. Record the result. Keep the plugin only if it is needed for another reason, and say so. |
| Not run | `pending` | No claim may be made. |
| Not applicable | `not-applicable` | Developer tooling, not a model-facing capability. |

A failed gate is a valid, useful result. It is recorded as-is. The cycle does not tune the plugin toward the threshold and then rerun.

### 3.5 Recording

- Commit a summary to `testing/eval/baselines/<name>-<category>-v1.json` (the baseline README says why these are committed).
- Raw runs under `testing/eval/runs/` stay gitignored.
- The PR description states the arms, model, seeds, task count, and gate result.

### 3.6 Certification at phase exit

Per plugin, a `measured-helpful` result is sufficient for "offered by default." At phase exit, run the full set on the held-out suite (human-owned) and the leave-one-out ablation (`testing/eval/run_ablation.py`). A plugin whose removal changes success by under 2 points is a candidate to drop, because it costs context without helping.

## 4. Levels

| Level | Requirement |
|---|---|
| Draft | L1 and L2 green |
| Verified | L1 to L4 green, perf within target |
| Certified | Verified, and L5 `measured-helpful` on the eval suite, and it holds on the held-out suite at phase exit |

## 5. Known state (as of this plan)

- Harness: L1 to L4 wired for `structural-anchor`, `symbol-navigator`, `lazy-dev`, and `loop-engineering-go`.
- L5 campaign completed with `qwen3:8b`, `SEEDS=3` (`harness.json` → `l5.model`, Makefile `OLLAMA_MODEL`).
- `measured-helpful`: `code-generation-helper` only.
- Most plugins are `measured-no-uplift`; dominant failure mode is hallucination rate up (`hall↑`).
- Held-out suite and ollama leave-one-out ablation (`testing/eval/run_ablation.py --agent ollama`) are still required before any plugin is **Certified**.
