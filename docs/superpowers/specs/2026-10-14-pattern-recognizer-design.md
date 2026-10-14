# pattern-recognizer: design (DRAFT)

> Status: DRAFT first pass. Generated for review. Tool names are proposals, not approved. `tools` in `docs/plan/plugins.json` stays `null` until a person approves this spec. Then the entry becomes `planned`.

## Purpose

`pattern-recognizer` belongs to phase 3 (Validation and testing). It is a Code search + ML plugin with complexity M and priority 1 in the reference matrix. Its job is to help a small local model make a deterministic, checkable decision it would otherwise guess at. It must give structured JSON, not prose.

Dependencies: `workspace-search`. Build order: 13. Eval category for L5: `multi-file`.

## Shared contract

- Every tool reads one JSON object on stdin and writes one JSON line on stdout (`io_mode: json`).
- `root_path` is required wherever a repo is read. `depth` defaults to 3. `skip_dirs` defaults to the standard set (`.git`, `node_modules`, `vendor`, `.venv`, `__pycache__`).
- Output is deterministic for the same input and repo state. Stdout is capped at 1 MB. Traversal caps are documented in the README.
- Caches go only under `~/.cache/naitv-mcp/pattern-recognizer/`. No network access.

## Performance target

`< 1s` (from the matrix; enforced once `harness.json` has a perf block).

## Tools (draft)

| Tool | Input | Output |
|---|---|---|
| `find_pattern_instances` | pattern_id, root_path | instances[], locations |
| `detect_repeated_patterns` | root_path, min_occurrences | patterns[], counts |
| `rank_examples` | pattern_id, root_path, limit | examples[] ranked |
| `pattern_summary` | pattern_id | summary, instance_count |

### `find_pattern_instances`

- Input: pattern_id, root_path, plus shared `root_path` where applicable.
- Output: one JSON object with instances[], locations.
- Timeout: set from the performance target (`< 1s`) with headroom.
- Errors: a structured `{"error": ..., "code": ...}` object for bad input. No tracebacks on stdout.

### `detect_repeated_patterns`

- Input: root_path, min_occurrences, plus shared `root_path` where applicable.
- Output: one JSON object with patterns[], counts.
- Timeout: set from the performance target (`< 1s`) with headroom.
- Errors: a structured `{"error": ..., "code": ...}` object for bad input. No tracebacks on stdout.

### `rank_examples`

- Input: pattern_id, root_path, limit, plus shared `root_path` where applicable.
- Output: one JSON object with examples[] ranked.
- Timeout: set from the performance target (`< 1s`) with headroom.
- Errors: a structured `{"error": ..., "code": ...}` object for bad input. No tracebacks on stdout.

### `pattern_summary`

- Input: pattern_id, plus shared `root_path` where applicable.
- Output: one JSON object with summary, instance_count.
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
- L4 MCP integration: `make l4 PLUGIN=pattern-recognizer`.
- L5 uplift: eval category `multi-file`, at least 10 dev tasks plus 2 controls, pre-registered gate, 3 seeds, pinned model. Held-out tasks are not touched.

## Out of scope

- Any behavior the reference matrix does not name for this plugin.
- Editing repo files. Read-only unless a tool's name and spec say otherwise.
- Plugins other than `pattern-recognizer`. Shared harness changes must be additive and listed in the PR.

## Open questions for review

- Confirm the tool list and counts (matrix gives 4 tools).
- Confirm the eval category `multi-file`.
- Confirm the timeout and cap values.
