# lint-fix-loop: design (DRAFT)

> Status: DRAFT first pass. Generated for review. Tool names are proposals, not approved. `tools` in `docs/plan/plugins.json` stays `null` until a person approves this spec. Then the entry becomes `planned`.

## Purpose

`lint-fix-loop` belongs to phase 3 (Validation and testing). It is a Linter wrappers plugin with complexity L and priority 1 in the reference matrix. Its job is to help a small local model make a deterministic, checkable decision it would otherwise guess at. It must give structured JSON, not prose.

Dependencies: `validate-and-test`. Build order: 20. Eval category for L5: `fix-with-tests`.

## Shared contract

- Every tool reads one JSON object on stdin and writes one JSON line on stdout (`io_mode: json`).
- `root_path` is required wherever a repo is read. `depth` defaults to 3. `skip_dirs` defaults to the standard set (`.git`, `node_modules`, `vendor`, `.venv`, `__pycache__`).
- Output is deterministic for the same input and repo state. Stdout is capped at 1 MB. Traversal caps are documented in the README.
- Caches go only under `~/.cache/naitv-mcp/lint-fix-loop/`. No network access.

## Performance target

`< 1s` (from the matrix; enforced once `harness.json` has a perf block).

## Tools (draft)

| Tool | Input | Output |
|---|---|---|
| `run_linter` | root_path, paths, linter | diagnostics[], exit_code |
| `apply_safe_fixes` | root_path, diagnostics | applied[], skipped[] |
| `summarize_lint_results` | diagnostics | summary, counts_by_rule |

### `run_linter`

- Input: root_path, paths, linter, plus shared `root_path` where applicable.
- Output: one JSON object with diagnostics[], exit_code.
- Timeout: set from the performance target (`< 1s`) with headroom.
- Errors: a structured `{"error": ..., "code": ...}` object for bad input. No tracebacks on stdout.

### `apply_safe_fixes`

- Input: root_path, diagnostics, plus shared `root_path` where applicable.
- Output: one JSON object with applied[], skipped[].
- Timeout: set from the performance target (`< 1s`) with headroom.
- Errors: a structured `{"error": ..., "code": ...}` object for bad input. No tracebacks on stdout.

### `summarize_lint_results`

- Input: diagnostics, plus shared `root_path` where applicable.
- Output: one JSON object with summary, counts_by_rule.
- Timeout: set from the performance target (`< 1s`) with headroom.
- Errors: a structured `{"error": ..., "code": ...}` object for bad input. No tracebacks on stdout.

## Failure modes

- Missing or unreadable `root_path`: structured error, exit 0 with `"error"` set.
- Repo larger than the traversal cap: partial result with `"truncated": true`, never a silent cut.
- Timeout: the harness kills the process. The tool must not write partial output.
- Unsupported language or file type: skipped and listed in `"skipped"`, not guessed.

## Test plan (profile `json_tools`)

- L1 unit tests for each tool, including bad input and truncation.
- L2 contract schema per tool under `testing/contract/schemas/`, inputs under `testing/fixtures/inputs/`.
- L3 golden output for at least one fixture repo, and a perf check against the target above.
- L4 MCP integration: `make l4 PLUGIN=lint-fix-loop`.
- L5 uplift: eval category `fix-with-tests`, at least 10 dev tasks plus 2 controls, pre-registered gate, 3 seeds, pinned model. Held-out tasks are not touched.

## Out of scope

- Any behavior the reference matrix does not name for this plugin.
- Editing repo files. Read-only unless a tool's name and spec say otherwise.
- Plugins other than `lint-fix-loop`. Shared harness changes must be additive and listed in the PR.

## Open questions for review

- Confirm the tool list and counts (matrix gives 3 tools).
- Confirm the eval category `fix-with-tests`.
- Confirm the timeout and cap values.
