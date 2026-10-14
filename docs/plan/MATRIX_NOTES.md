# Matrix conversion notes

Source: `PLUGIN_REFERENCE_MATRIX.md` (supplied by the user, copied unchanged next to this file). The catalog in `plugins.json` is derived from it. This file records every decision made in the conversion, so each one can be checked and reversed.

## 1. What the matrix contains

| Item | Matrix says | Rows actually present |
|---|---|---|
| Plugins | "67" in the header, "68" in the phase table | 64 plugin rows |
| Infrastructure rows | not counted | `naitv-mcp-core` (Phase 1), `py-template`, `go-template`, `sh-template` (Phase 1) |
| Total tools | 244 | row sum is 245 (off by one; not resolved, no plan depends on it) |

The 64 plugin rows are 1 in Phase 1 (`plugin-manager`) plus 8, 10, 10, 15, and 20 in Phases 2 to 6.

## 2. What was excluded, and what was added

- **`naitv-mcp-core`** is excluded. It is naitv-mcp itself. JSON I/O is already in core (see ARCHITECTURE.md).
- **`py-template`, `go-template`, `sh-template`** are excluded. `scripts/scaffold_plugin.sh` replaces them, with a `json_tools`, `rules_only`, or `mixed` profile.
- **`lazy-dev` and `loop-engineering-go`** are added as phase 0. They are repo plugins that predate the matrix. They are not in it.

## 3. What the matrix does not give us

- **Tool names.** The matrix gives a count per plugin. Names exist only for the handful of plugins mentioned in the earlier planning summaries (below). The other 61 entries are `needs-spec`. Spec PRs are the way to fix that (CYCLE_PROMPT step 2b).
- **Eval categories.** The matrix has none. The `eval_category` values in `plugins.json` are my proposal, based on what each plugin is for. Categories follow TESTING.md section 3. Model-facing plugins get a category. Infrastructure and reporting plugins get `null` and `l5: not-applicable`: `cache-manager` and `team-metrics-collector`.
- **Summary statistics.** The complexity, priority, and category tables in the matrix do not reconcile with the rows. The per-row values are used. The summaries are not.

Tool names taken from an earlier planning summary (not verified against the matrix): `context-injector` → `get_code_slice`; `lint-fix-loop` → `run_linter`; `tdd-runner` → `run_tests`; `doc-scraper` → `fetch_and_parse`; `workspace-search` → `semantic_search`; `plugin-manager` → `list_plugins`, `validate_plugin`, `test_plugin`.

## 4. Dependency normalization

The matrix's "Depends On" column uses short names that do not always match a plugin row. Each normalization below is recorded in the entry's `depends_on_raw` and `notes`.

| Matrix says | Normalized to | Used by |
|---|---|---|
| `Plugin framework` | no dependency (naitv-mcp core) | structural-anchor, blame-context-historian, build-system-integrator, doc-scraper, workspace-search, cache-manager, secrets-detector, license-compliance-checker |
| `semantic-search` | `workspace-search` (**ambiguous, confirm**) | decision-log-runner |
| `code-style` | `code-style-enforcer` | naming-validator, logging-enforcer, language-idioms-enforcer |
| `team-knowledge` | `team-knowledge-extractor` | code-style-enforcer, invariant-checker |
| `build-system` | `build-system-integrator` | validate-and-test, performance-profiler, benchmark-generator |
| `dependency-graph` | `dependency-graph-analyzer` | circular-dependency-detector, change-impact-analyzer |
| `api-contract` | `api-contract-validator` | contract-testing-helper |
| `change-impact` | `change-impact-analyzer` | rollback-plan-generator |

Every normalized name exists as a plugin row. After normalization, every dependency resolves to a catalog entry.

## 5. Phase-order exceptions (dependency in a later phase)

These are warnings in `catalog_check.py`. The build cycle still refuses to build an entry until its dependencies are `exists`, so these entries simply wait. They are listed so someone can decide whether the phase order or the dependency should change.

| Plugin (phase) | Depends on (phase) |
|---|---|
| decision-log-runner (2) | workspace-search (4) |
| code-review-simulator (2) | code-style-enforcer (4) |
| mistake-tracker (3) | cache-manager (4) |
| pattern-recognizer (3) | workspace-search (4) |
| naming-validator (3) | code-style-enforcer (4) |
| rollback-plan-generator (5) | change-impact-analyzer (6) |

Moving `cache-manager` and `workspace-search` into Phase 3 would clear two exceptions (mistake-tracker and pattern-recognizer). The other four need `code-style-enforcer`, `change-impact-analyzer`, or `workspace-search` to move earlier than their dependents. Which phase changes, if any, is a sequencing decision for you, not for the cycle.

## 6. Priority and complexity

Both are copied per row from the matrix (`complexity`, `priority`). Priority 1 is critical, 2 is important, and 3 is nice to have.

## 7. Performance targets

Copied per row (`perf`). Targets for `structural-anchor` and `symbol-navigator` are also enforced in their `harness.json`. The other targets are not enforced until their plugin is built and gets a perf block.
