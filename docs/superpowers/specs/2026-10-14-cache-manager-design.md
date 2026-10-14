# cache-manager: design (DRAFT)

> Status: DRAFT first pass. Generated for review. Tool names are proposals, not approved. `tools` in `docs/plan/plugins.json` stays `null` until a person approves this spec. Then the entry becomes `planned`.

## Purpose

`cache-manager` belongs to phase 4 (Context, search and safety). It is a In-memory + SQLite plugin with complexity M and priority 1 in the reference matrix. Its job is to help a small local model make a deterministic, checkable decision it would otherwise guess at. It must give structured JSON, not prose.

Dependencies: none (naitv-mcp core only). Build order: 10. Eval category for L5: `none (infrastructure or reporting; L5 not-applicable)`.

## Shared contract

- Every tool reads one JSON object on stdin and writes one JSON line on stdout (`io_mode: json`).
- `root_path` is required wherever a repo is read. `depth` defaults to 3. `skip_dirs` defaults to the standard set (`.git`, `node_modules`, `vendor`, `.venv`, `__pycache__`).
- Output is deterministic for the same input and repo state. Stdout is capped at 1 MB. Traversal caps are documented in the README.
- Caches go only under `~/.cache/naitv-mcp/cache-manager/`. No network access.

## Performance target

`< 100ms` (from the matrix; enforced once `harness.json` has a perf block).

## Tools (draft)

| Tool | Input | Output |
|---|---|---|
| `cache_get` | key, namespace | hit, value |
| `cache_put` | key, namespace, value, ttl | stored |
| `cache_stats` | namespace | entries, bytes, hit_rate |
| `cache_prune` | namespace, max_bytes | removed, remaining |

### `cache_get`

- Input: key, namespace, plus shared `root_path` where applicable.
- Output: one JSON object with hit, value.
- Timeout: set from the performance target (`< 100ms`) with headroom.
- Errors: a structured `{"error": ..., "code": ...}` object for bad input. No tracebacks on stdout.

### `cache_put`

- Input: key, namespace, value, ttl, plus shared `root_path` where applicable.
- Output: one JSON object with stored.
- Timeout: set from the performance target (`< 100ms`) with headroom.
- Errors: a structured `{"error": ..., "code": ...}` object for bad input. No tracebacks on stdout.

### `cache_stats`

- Input: namespace, plus shared `root_path` where applicable.
- Output: one JSON object with entries, bytes, hit_rate.
- Timeout: set from the performance target (`< 100ms`) with headroom.
- Errors: a structured `{"error": ..., "code": ...}` object for bad input. No tracebacks on stdout.

### `cache_prune`

- Input: namespace, max_bytes, plus shared `root_path` where applicable.
- Output: one JSON object with removed, remaining.
- Timeout: set from the performance target (`< 100ms`) with headroom.
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
- L4 MCP integration: `make l4 PLUGIN=cache-manager`.
- L5 uplift: not-applicable (no eval category). Held-out tasks are not touched.

## Out of scope

- Any behavior the reference matrix does not name for this plugin.
- Editing repo files. Read-only unless a tool's name and spec say otherwise.
- Plugins other than `cache-manager`. Shared harness changes must be additive and listed in the PR.

## Open questions for review

- Confirm the tool list and counts (matrix gives 4 tools).
- Confirm the eval category `None`.
- Confirm the timeout and cap values.
