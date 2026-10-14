# build-system-integrator: design (DRAFT)

> Status: DRAFT first pass. Generated for review. Tool names are proposals, not approved. `tools` in `docs/plan/plugins.json` stays `null` until a person approves this spec. Then the entry becomes `planned`.

## Purpose

`build-system-integrator` belongs to phase 3 (Validation and testing). It is a Build wrappers plugin with complexity L and priority 1 in the reference matrix. Its job is to help a small local model make a deterministic, checkable decision it would otherwise guess at. It must give structured JSON, not prose.

Dependencies: none (naitv-mcp core only). Build order: 6. Eval category for L5: `fix-with-tests`.

## Shared contract

- Every tool reads one JSON object on stdin and writes one JSON line on stdout (`io_mode: json`).
- `root_path` is required wherever a repo is read. `depth` defaults to 3. `skip_dirs` defaults to the standard set (`.git`, `node_modules`, `vendor`, `.venv`, `__pycache__`).
- Output is deterministic for the same input and repo state. Stdout is capped at 1 MB. Traversal caps are documented in the README.
- Caches go only under `~/.cache/naitv-mcp/build-system-integrator/`. No network access.

## Performance target

`< 5s` (from the matrix; enforced once `harness.json` has a perf block).

## Tools (draft)

| Tool | Input | Output |
|---|---|---|
| `detect_build_tool` | root_path | tool, config_files[] |
| `list_build_targets` | root_path | targets[] |
| `run_build_target` | root_path, target | exit_code, output_tail |
| `parse_build_errors` | output | errors[] with file, line, message |

### `detect_build_tool`

- Input: root_path, plus shared `root_path` where applicable.
- Output: one JSON object with tool, config_files[].
- Timeout: set from the performance target (`< 5s`) with headroom.
- Errors: a structured `{"error": ..., "code": ...}` object for bad input. No tracebacks on stdout.

### `list_build_targets`

- Input: root_path, plus shared `root_path` where applicable.
- Output: one JSON object with targets[].
- Timeout: set from the performance target (`< 5s`) with headroom.
- Errors: a structured `{"error": ..., "code": ...}` object for bad input. No tracebacks on stdout.

### `run_build_target`

- Input: root_path, target, plus shared `root_path` where applicable.
- Output: one JSON object with exit_code, output_tail.
- Timeout: set from the performance target (`< 5s`) with headroom.
- Errors: a structured `{"error": ..., "code": ...}` object for bad input. No tracebacks on stdout.

### `parse_build_errors`

- Input: output, plus shared `root_path` where applicable.
- Output: one JSON object with errors[] with file, line, message.
- Timeout: set from the performance target (`< 5s`) with headroom.
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
- L4 MCP integration: `make l4 PLUGIN=build-system-integrator`.
- L5 uplift: eval category `fix-with-tests`, at least 10 dev tasks plus 2 controls, pre-registered gate, 3 seeds, pinned model. Held-out tasks are not touched.

## Out of scope

- Any behavior the reference matrix does not name for this plugin.
- Editing repo files. Read-only unless a tool's name and spec say otherwise.
- Plugins other than `build-system-integrator`. Shared harness changes must be additive and listed in the PR.

## Open questions for review

- Confirm the tool list and counts (matrix gives 4 tools).
- Confirm the eval category `fix-with-tests`.
- Confirm the timeout and cap values.
