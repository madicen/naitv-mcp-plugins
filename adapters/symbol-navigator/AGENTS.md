# Symbol Navigator — precise defs and heuristic refs

<!-- Universal adapter for the symbol-navigator plugin. Copy this file into any project
     root (or your agent's global instructions) for agents that read AGENTS.md.
     Keep this text aligned with plugins/symbol-navigator.json — the plugin JSON is
     the source of truth. -->

After you have oriented (e.g. with structural-anchor's project map), use these tools for symbol-level navigation instead of broad grep:

1. **find_symbol_definition** — `root_path` + `symbol` (optional `kind` filter).
2. **search_by_pattern** — regex over indexed symbol names.
3. **get_symbol_references** — uses of a symbol; optional `file_path` to scope nearby files first.

**Not a replacement for gopls.** References are AST/heuristic (`heuristic: true`); same-name false positives are possible.

Warm lookups (cached index) target **&lt;100ms**; the first call on a tree may build the index and take longer. Install the tool bundle before first use (see `tools/symbol-navigator/README.md` in the plugin repo). Index cache: `~/.cache/naitv-mcp/symbol-navigator/`.
