# structural-anchor

Codebase structural map for naitv-mcp agents — packages, symbols, languages, and statistics for Python and Go projects.

## Install

Symlink this directory into the naitv-mcp tools path:

```bash
mkdir -p ~/.config/naitv-mcp/tools
ln -s "$(pwd)/tools/structural-anchor" ~/.config/naitv-mcp/tools/structural-anchor
```

From the plugin repo root, `$(pwd)` resolves to the checkout. Adjust if you clone elsewhere.

## Tools (via `TOOL_NAME`)

The script reads one JSON line from stdin and writes one JSON line to stdout. naitv-mcp sets `TOOL_NAME` when invoking via `run_tool`.

| `TOOL_NAME` | Description |
|-------------|-------------|
| `get_project_map` | Flattened packages + symbols map |
| `list_languages` | Language file/line counts and primary language |
| `get_codebase_statistics` | Size and complexity metrics |

### Parameters (stdin JSON)

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `root_path` | yes | — | Absolute path to the project root |
| `depth` | no | `3` | Max directory walk depth (root = 0) |
| `skip_dirs` | no | see below | Directory basenames to prune |

Default `skip_dirs`: `node_modules`, `.git`, `vendor`, `.venv`, `dist`, `build`, `__pycache__`.

## Cache

Results are cached under:

```
~/.cache/naitv-mcp/structural-anchor/<key>.json
```

The cache key combines `root_path`, `depth`, `skip_dirs`, and a git commit fingerprint (HEAD SHA, or index mtime, or directory hash fallback). Repeated calls with the same fingerprint return `"cached": true`.

Go symbol extraction builds a helper binary into `~/.cache/naitv-mcp/bin/` when needed.

## Examples

From the repo root (after install or from this directory):

```bash
# Full project map
echo '{"root_path":"/path/to/project","depth":3}' | \
  TOOL_NAME=get_project_map python3 structural_anchor.py

# Languages only
echo '{"root_path":"/path/to/project"}' | \
  TOOL_NAME=list_languages python3 structural_anchor.py

# Statistics only
echo '{"root_path":"/path/to/project"}' | \
  TOOL_NAME=get_codebase_statistics python3 structural_anchor.py
```

See `examples/sample_input.json` for a minimal payload.

## Go support (optional)

Go symbol extraction requires the `go` toolchain on `PATH`. If Go is unavailable or the build fails, Python-only results are returned and a warning is printed to stderr — the tool does not fail entirely.

## Plugin install

Install the naitv-mcp plugin (registers the three tools and an init rule):

```
install_plugin(name="structural-anchor")
```

Or copy the universal adapter from `adapters/structural-anchor/AGENTS.md` for non-MCP agents.
