# symbol-navigator — Design Spec

**Date:** 2026-09-13  
**Phase:** 2 (second context plugin; structural-anchor exists)  
**Status:** Approved for implementation planning  

## Problem

After orienting with a project map, agents still need precise “where is X defined?” and “where is X used?” answers. Grep is noisy; full LSP is accurate but cold-starts too slowly for a per-call MCP tool. `symbol-navigator` provides fast AST-based definition and reference lookup for Go and Python.

## Goals

- Three MCP tools: `find_symbol_definition`, `search_by_pattern`, `get_symbol_references`
- **AST-first** (no LSP in v1); languages: **Go + Python only**
- Independent package (does not import or shell out to structural-anchor)
- Warm (cached-index) lookups **< 100ms**; cold index build may exceed that
- Same JSON I/O + B1 `TOOL_NAME` packaging as structural-anchor
- Heuristic but useful references (scoped preference, documented false positives)

## Non-goals (v1)

- LSP / gopls / pylsp / typescript-language-server
- TypeScript / JavaScript
- Perfect cross-package rename safety or IDE-grade ref accuracy
- Calling structural-anchor tools or sharing its Python modules
- Persistent daemon processes

## Architecture

```
plugins/symbol-navigator.json
tools/symbol-navigator/
  symbol_navigator.py           # stdin JSON, TOOL_NAME dispatch, cache, Python AST
  go_nav/                       # tiny Go helper (go/parser + go/ast)
    main.go
    go.mod
  tests/
  examples/
adapters/symbol-navigator/AGENTS.md
```

**Runtime flow**

1. MCP entry runs `sh -c` with `TOOL_NAME=<entry>` and `io_mode=json`.
2. Python reads one JSON object from stdin.
3. Ensure symbol **index** cache under `~/.cache/naitv-mcp/symbol-navigator/` (defs only).
4. Serve the requested tool from the index (defs / pattern) or a scoped ref scan.
5. Write JSON to stdout; exit 0 on not-found (empty collections).

**Dispatch (B1):**

```text
TOOL_NAME=find_symbol_definition python3 ~/.config/naitv-mcp/tools/symbol-navigator/symbol_navigator.py
```

Missing/unknown `TOOL_NAME` → stderr + exit 1.

**Relationship to structural-anchor:** ecosystem dependency only (“plugin exists”). Duplicate walk/parse conventions intentionally; no code import.

## Tool contracts

### Shared input

| Field | Required | Default | Meaning |
|-------|----------|---------|---------|
| `root_path` | yes | — | Project root to search |
| `depth` | no | `3` | Hard directory walk depth (root = 0) |
| `skip_dirs` | no | see below | Basename prune set |

Default `skip_dirs`: `node_modules`, `.git`, `vendor`, `.venv`, `dist`, `build`, `__pycache__`.  
Also prune dirs whose names start with `.`.  
Normalize `skip_dirs` from MCP: accept JSON array, comma-separated string, or list; never char-split a string; empty/invalid → defaults.

Source files: `.py`, `.go` only.

### `find_symbol_definition`

**Extra params:** `symbol` (required), `kind` (optional filter).

**Success (single / best match):**

```json
{
  "file": "src/auth/user_service.go",
  "line": 42,
  "column": 6,
  "type": "type",
  "signature": "type UserService struct",
  "receivers": [],
  "imports": ["database/sql", "fmt"],
  "source": "ast",
  "cached": true
}
```

**Ambiguous:** also include `matches` array of the same shape (without requiring `receivers`/`imports` on every entry). Prefer exported / exact name / kind filter; if still multiple, return the first by `(file, line)` sort and list all in `matches`.

**Not found:** `{ "matches": [], "cached": true }` exit 0.

- `column`: 1-based when known; `0` if unknown.
- `receivers`: Go methods only (type names); else `[]` or omit.
- `imports`: file-level imports of the defining file when cheap; else `[]`.
- `type`: symbol kind string (`function`, `method`, `class`, `type`, `interface`, `const`, `var`).

### `search_by_pattern`

**Extra params:** `pattern` (required regex), `kind` (optional).

```json
{
  "results": [
    {
      "name": "UserService",
      "kind": "type",
      "file": "src/auth/user_service.go",
      "line": 42,
      "signature": "type UserService struct"
    }
  ],
  "cached": true
}
```

Invalid regex → stderr + exit 1. Empty results → `results: []`, exit 0.

### `get_symbol_references`

**Extra params:** `symbol` (required), `file_path` (optional hint for scoping).

```json
{
  "definition": { "file": "...", "line": 42, "column": 6, "type": "type", "signature": "..." },
  "references": [
    { "file": "src/auth/handler.go", "line": 10, "column": 12, "context": "svc := UserService{}" }
  ],
  "cached": false,
  "heuristic": true
}
```

**Scoping (B):**

1. Resolve definition(s) via the index.
2. If `file_path` given, scan that file’s directory / package first.
3. Then scan remaining walked `.py`/`.go` files.
4. Match identifier tokens / AST `Name` / `Attribute` / selector bases equal to `symbol` (language-appropriate). Exclude the definition span itself from `references` (definition only under `definition`).
5. Always set `"heuristic": true` in v1 so agents know this is not gopls.

False positives (same name, different binding) are accepted and documented.

## Index & caching

| Item | Location |
|------|----------|
| Symbol index cache | `~/.cache/naitv-mcp/symbol-navigator/` |
| Go helper binary | `~/.cache/naitv-mcp/bin/go-nav` |

**Index contents:** flattened defs `{name, kind, file, line, column, signature, receivers?, imports?}`.  
**Cache key:** `sha256(canonical_root|depth|sorted(skip_dirs)|fingerprint)`.  
**Fingerprint:** `git rev-parse HEAD` plus dirty marker from `git status --porcelain` when in a git repo; else index-mtime / top-level mtime hash (same spirit as structural-anchor).  
**Invalidation:** fingerprint mismatch only (no TTL).  
**Warm path:** load index JSON, answer query in-process — **this** is the <100ms SLA.  
**Cold path:** walk + parse + write cache; may exceed 100ms; still should feel snappy on small/medium trees.

Do not cache a degraded Go index when `.go` files exist but the helper failed (avoid poisoning); Python-only indexes may still cache.

## Parsing

### Python

- Stdlib `ast`
- Extract nested classes/methods (recurse `ClassDef` bodies)
- Full arg signatures (`posonlyargs`, `args`, `vararg`, `kwonlyargs`, `kwarg`)
- References: walk AST for `Name` / `Attribute.attr` matching the symbol

### Go

- Helper `go_nav` using `go/parser` + `go/ast`
- Defs: functions, methods (signature includes receiver), types, interfaces, exported const/var
- References: identifier / selector scans in batch over file list
- If `go` unavailable: Go defs/refs empty; Python still works; warn on stderr; exit 0

### TypeScript / LSP

Deferred. README states: “Not a replacement for gopls; v1 is AST + heuristics.”

## Plugin entry shape

Three `kind=tool` entries in `plugins/symbol-navigator.json`:

- `io_mode`: `json`
- `timeout`: `30s` (cold builds); warm queries finish far sooner
- `params` as above per tool
- `exec`: `TOOL_NAME=<name> python3 ~/.config/naitv-mcp/tools/symbol-navigator/symbol_navigator.py`

Optional `init` rule: after structural-anchor (or when seeking a specific symbol), prefer these tools over blind grep.

Register in `registry.json`; document symlink install like structural-anchor.

## Error handling

| Case | Behavior |
|------|----------|
| Bad/missing JSON, missing required fields | stderr + exit 1 |
| Invalid regex | stderr + exit 1 |
| Unknown `TOOL_NAME` | stderr + exit 1 |
| Symbol / pattern not found | empty collections, exit 0 |
| Unreadable / unparseable file | skip; continue |
| No `go` toolchain | warn; Python-only results; exit 0 |

## Testing

- Unit: Python extract + refs; pattern filter; skip_dirs normalization; dirty fingerprint
- Go helper: golden defs + refs on `testdata/`
- Dispatch: all three `TOOL_NAME`s via stdin JSON
- Perf: warm `find_symbol_definition` on fixture < 100ms
- Integration: this repo (Python + any Go under `tools/`)

## Success criteria

- [ ] Accurate Go/Python definitions on fixtures + this repo
- [ ] Pattern search returns regex-filtered defs
- [ ] References returned with `heuristic: true` and scoping behavior
- [ ] Warm lookup < 100ms on fixture
- [ ] Plugin JSON + registry + README + adapter
- [ ] jj commits per logical change (no `git commit` for local history)

## Dependencies

- Phase 1 JSON I/O — done
- structural-anchor — must exist in the ecosystem (merged); not a runtime import
- Python 3 stdlib; Go toolchain optional for full Go support

## Follow-ups

- Persistent gopls/pylsp daemon mode for IDE-grade refs
- TypeScript via tree-sitter or tsserver
- Optional read-through of structural-anchor cache to skip a second walk
