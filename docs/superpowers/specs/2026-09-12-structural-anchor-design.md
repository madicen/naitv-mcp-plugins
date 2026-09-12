# structural-anchor — Design Spec

**Date:** 2026-09-12  
**Phase:** 2 (first plugin after Phase 1 JSON I/O)  
**Status:** Approved for implementation planning  

## Problem

Agents thrash when exploring large codebases: they grep and open files without a compact map of packages and symbols. `structural-anchor` gives a flattened, cached structural index so models can orient in one tool call.

## Goals

- Three MCP tools: `get_project_map`, `list_languages`, `get_codebase_statistics`
- Accurate symbols for **Python** and **Go** in v1 (TypeScript/JavaScript deferred)
- Cold map build **< 2s** on ~50K-file trees when skip/prune dominates; warm cache **< 100ms**
- Graceful degradation (skip bad files; Go symbols optional if `go` missing)
- Ship as naitv-mcp plugin JSON + JSON I/O scripts (Phase 1 `io_mode=json`)

## Non-goals (v1)

- `validate_structure`
- TypeScript/JavaScript AST (tree-sitter later)
- Linux kernel as CI gate (manual bench only)
- Full AST / bodies / references (symbol-navigator / context-injector own that)

## Architecture

```
plugins/structural-anchor.json
tools/structural-anchor/
  structural_anchor.py          # orchestrator + Python ast + cache + dispatch
  go_symbols/                   # tiny Go helper (go/parser)
    main.go
    go.mod
  tests/
  examples/
adapters/structural-anchor/AGENTS.md   # optional compact init-rule fallback
```

**Runtime flow**

1. MCP tool entry runs `sh -c` with `TOOL_NAME=<entry>` and `io_mode=json`.
2. Python reads one JSON object from stdin.
3. Cache lookup under `~/.cache/naitv-mcp/structural-anchor/`.
4. On miss: depth-limited walk → parse → write cache → stdout JSON.
5. On hit: project map from cache; tool-specific projection; `cached: true`.

**Dispatch (B1):** entry name drives behavior via `TOOL_NAME` baked into each entry’s `exec` (naitv-mcp does not inject this today):

```text
TOOL_NAME=get_project_map python3 ~/.config/naitv-mcp/tools/structural-anchor/structural_anchor.py
```

Missing/unknown `TOOL_NAME` → stderr + exit 1.

## Tool contracts

### Shared input

| Field | Required | Default | Meaning |
|-------|----------|---------|---------|
| `root_path` | yes | — | Absolute or resolvable path to analyze |
| `depth` | no | `3` | Max **directory walk** depth from `root_path` |
| `skip_dirs` | no | see below | Directory basenames to prune |

Default `skip_dirs`: `node_modules`, `.git`, `vendor`, `.venv`, `dist`, `build`, `__pycache__`.

Also prune any directory whose name starts with `.` (in addition to `skip_dirs`).

### Depth semantics

- **Hard stop:** nothing past `depth` is walked or analyzed.
- Stats and symbols reflect **only** what the walk found.
- `depth` does **not** limit AST nesting inside a parsed file (nested classes/methods included).

### `get_project_map`

Returns:

```json
{
  "packages": [
    {
      "name": "mypackage",
      "path": "src/mypackage",
      "symbols": [
        {
          "name": "MyFunction",
          "kind": "function",
          "signature": "def MyFunction(x: int) -> str",
          "line": 42
        }
      ]
    }
  ],
  "languages": ["go", "python"],
  "statistics": { "...": "see statistics shape" },
  "cached": false,
  "commit": "abc123…"
}
```

- `commit`: HEAD hash when `.git` exists; **omit** field otherwise (no `git_available` flag).
- `cached`: whether this response was served from cache.

### `list_languages`

```json
{
  "languages": [
    {"id": "go", "file_count": 800, "line_count": 40000},
    {"id": "python", "file_count": 400, "line_count": 10000}
  ],
  "primary": "go",
  "cached": true,
  "commit": "abc123…"
}
```

`primary` = language with highest `file_count` (ties: first by sorted id).

### `get_codebase_statistics`

Returns the shared `statistics` object (plus `cached` / optional `commit`):

```json
{
  "total_files": 1234,
  "total_lines": 50000,
  "complexity": 4.5,
  "packages": 42,
  "parse_errors": 3,
  "by_language": {
    "go": {"files": 800, "lines": 40000, "complexity": 4.2},
    "python": {"files": 400, "lines": 10000, "complexity": 3.1}
  },
  "cached": false,
  "commit": "abc123…"
}
```

- `complexity` (top-level): global mean over parsed functions.
- `by_language.*.complexity`: per-language mean (same metric).
- Metric: approximate cyclomatic (decision nodes + 1) averaged over functions; `0` if none. Document as approximate.

### Symbol kinds (v1)

| Kind | Python | Go |
|------|--------|-----|
| `function` | module-level `def` / `async def` | package-level `func` |
| `method` | methods inside class | methods with receiver |
| `class` | `class` | — |
| `type` | — | named `type` decls (non-interface) |
| `interface` | — | `interface` types |
| `const` | — (skipped in v1) | exported `const` |
| `var` | — (skipped in v1) | exported `var` |

No function bodies, no import graphs, no references.

### Language detection

Extension map for v1: `.py` → `python`, `.go` → `go`.  
`total_files` / `total_lines` / language stats count **only** those source files under the depth-limited walk (not every file on disk).

## Parsing

### Python

- Stdlib `ast`
- Extract classes, functions, methods with signatures and line numbers
- Parallel parse with a small thread pool (4–8 workers)

### Go

- Helper module `tools/structural-anchor/go_symbols` using `go/parser` + `go/ast`
- Python ensures binary at `~/.cache/naitv-mcp/bin/go-symbols` via `go build` when missing or source newer than binary
- One helper invocation per map build: stdin = JSON list of file paths; stdout = symbols grouped by package path
- If `go` unavailable: count `.go` files for languages/stats; leave Go symbols empty; print warning on stderr; **exit 0** with valid JSON

### TypeScript/JavaScript

Deferred. Do not depend on tree-sitter in v1.

## Caching

| Item | Location |
|------|----------|
| Map cache | `~/.cache/naitv-mcp/structural-anchor/` |
| Go binary | `~/.cache/naitv-mcp/bin/go-symbols` |

**Cache key:** `sha256(canonical_root_path + depth + sorted(skip_dirs) + fingerprint)`

**Fingerprint:**

1. `git rev-parse HEAD` if git repo
2. Else mtime of `.git/index` if present
3. Else best-effort hash of top-level entry names + mtimes

**Value:** full `get_project_map` payload (other tools project from it).  
**Invalidation:** fingerprint mismatch only (no TTL).  
**All three tools** share one cache entry.

## Performance strategy

- `os.scandir` + prune early
- Hard depth clip
- Batch Go parse; parallel Python parse
- Cache warm path: read JSON + project fields
- Perf smoke in CI on small fixture; optional manual large-repo bench (not CI)

## Plugin entry shape

Three `kind=tool` entries in `plugins/structural-anchor.json`:

- `io_mode`: `json` (alias `ioMode` accepted by naitv-mcp)
- `timeout`: `30s`
- `params`: `root_path` (required), `depth`, `skip_dirs`
- `exec`: `TOOL_NAME=<name> python3 <install-path>/structural_anchor.py`

Install path documented as copy/symlink of `tools/structural-anchor/` into `~/.config/naitv-mcp/tools/structural-anchor/` (same pattern as Phase 1 examples). Registry entry added to `registry.json`.

Optional `init` rule: prefer calling structural-anchor before broad file thrashing.

## Error handling

| Case | Behavior |
|------|----------|
| Bad/missing JSON or `root_path` | stderr + exit 1 |
| Unreadable / unparseable file | skip; increment `parse_errors`; continue |
| No `go` toolchain | warn stderr; empty Go symbols; exit 0 |
| Unknown `TOOL_NAME` | stderr + exit 1 |
| Timeout | naitv-mcp kills process |

## Testing

- Unit: Python extractors, cache hit/miss, `TOOL_NAME` dispatch
- Go helper: golden on `testdata/` package
- Integration: this repo via stdin JSON → shape assertions
- Perf smoke: synthetic fixture; soft wall-clock budget (relaxed under load)
- No Linux-kernel CI job

## Success criteria

- [ ] Accurate Python + Go symbol map on this repo
- [ ] Three tools registered via plugin JSON; JSON I/O contract honored
- [ ] Cache hit returns `cached: true` and same fingerprint behavior
- [ ] Cold path designed for <2s on large pruned trees; measured on fixture + this repo
- [ ] Errors skip files without failing the tool
- [ ] Well-tested (unit + integration + helper golden)

## Dependencies

- Phase 1 complete (`io_mode=json` in naitv-mcp) — **done**
- Python 3 stdlib only for orchestrator
- Go toolchain optional at runtime (required to build `go_symbols` for full Go symbols)

## Out of scope follow-ups

- tree-sitter TS/JS
- `validate_structure`
- Incremental per-file cache
- LSP-backed accuracy
