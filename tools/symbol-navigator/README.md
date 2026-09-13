# symbol-navigator

AST-based symbol definition lookup, regex pattern search, and heuristic reference scans for naitv-mcp agents — **Go and Python only** in v1.

**Not a replacement for gopls** (or pylsp). Definitions come from parsing; references are identifier/heuristic scans with `"heuristic": true`. Expect occasional false positives when the same name appears in unrelated bindings.

## Install

Symlink this directory into the naitv-mcp tools path:

```bash
mkdir -p ~/.config/naitv-mcp/tools
ln -s "$(pwd)/tools/symbol-navigator" ~/.config/naitv-mcp/tools/symbol-navigator
```

From the plugin repo root, `$(pwd)` resolves to the checkout. Adjust if you clone elsewhere.

## Performance

- **Warm path (cached index):** lookups should complete in **&lt;100ms** — this is the SLA agents should rely on for per-call MCP use.
- **Cold path:** first request on a tree walks sources, builds the symbol index, and may exceed 100ms; results are cached under `~/.cache/naitv-mcp/symbol-navigator/` keyed by git fingerprint.

## Tools (via `TOOL_NAME`)

The script reads one JSON line from stdin and writes one JSON line to stdout. naitv-mcp sets `TOOL_NAME` when invoking via `run_tool`.

| `TOOL_NAME` | Description |
|-------------|-------------|
| `find_symbol_definition` | Best match for a symbol name (+ optional kind) |
| `search_by_pattern` | Regex filter over indexed symbol names |
| `get_symbol_references` | Heuristic uses of a symbol (+ optional `file_path` scope) |

### Parameters (stdin JSON)

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `root_path` | yes | — | Absolute path to the project root |
| `depth` | no | `3` | Max directory walk depth (root = 0) |
| `skip_dirs` | no | see below | Directory basenames to prune |

Default `skip_dirs`: `node_modules`, `.git`, `vendor`, `.venv`, `dist`, `build`, `__pycache__`.  
`skip_dirs` accepts a JSON list, a comma-separated string, or a JSON-array string.

**find_symbol_definition:** `symbol` (required), `kind` (optional).

**search_by_pattern:** `pattern` (required regex on names), `kind` (optional).

**get_symbol_references:** `symbol` (required), `file_path` (optional hint — search that file's directory first).

## Cache and Go helper

| Item | Location |
|------|----------|
| Symbol index | `~/.cache/naitv-mcp/symbol-navigator/` |
| Go helper binary | `~/.cache/naitv-mcp/bin/go-nav` (built on demand) |

If `.go` files exist but the Go helper cannot be built, degraded Go results are not cached (Python may still cache).

## Examples

```bash
echo '{"root_path":"/path/to/project","symbol":"UserService"}' | \
  TOOL_NAME=find_symbol_definition python3 symbol_navigator.py

echo '{"root_path":"/path/to/project","pattern":"^User"}' | \
  TOOL_NAME=search_by_pattern python3 symbol_navigator.py

echo '{"root_path":"/path/to/project","symbol":"UserService","file_path":"src/auth/handler.go"}' | \
  TOOL_NAME=get_symbol_references python3 symbol_navigator.py
```

See `examples/sample_input.json` for a minimal payload.

## Go support (optional)

Go definitions and references require the `go` toolchain on `PATH` to build/run `go-nav`. If Go is unavailable, Python-only results are returned with a stderr warning — the tool does not fail entirely.

## Plugin install

```
install_plugin(name="symbol-navigator")
```

Or copy the universal adapter from `adapters/symbol-navigator/AGENTS.md` for non-MCP agents.
