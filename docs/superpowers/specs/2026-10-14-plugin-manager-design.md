# plugin-manager — Design Spec

**Date:** 2026-10-14  
**Phase:** 1  
**Status:** Approved for implementation (catalog `planned`)  

## Problem

Plugin authors need a fast, local way to list manifests under a plugins tree, validate them against the entry contract, and run a bounded test pass — without installing into a live naitv-mcp store.

## Core overlap note

naitv-mcp core already ships `list_plugins` (installed plugins in the store), plus `install_plugin` / `uninstall_plugin` / `list_available_plugins`. It does **not** ship `validate_plugin` or `test_plugin`.

This plugin keeps the catalog tool name `list_plugins` but scopes it to **filesystem manifests** under `root_path` (developer tooling). Installing both core and this plugin into one MCP session may collide on the name; a human may rename later. Do not change the catalog name in this change.

## Goals

- Three JSON I/O tools: `list_plugins`, `validate_plugin`, `test_plugin`
- Stdlib-only Python; one JSON line out; diagnostics on stderr
- `list_plugins` / `validate_plugin` typically **< 1s** on a normal plugins tree
- `test_plugin` default mode is in-process lint (**< 1s**); optional `layers: "l2"` shells out to the contract runner (longer timeout)
- Deterministic; no network; no writes except optional cache under `~/.cache/naitv-mcp/plugin-manager/` (unused in v1)

## Non-goals (v1)

- Install / uninstall / registry fetch (core owns those)
- Running full L3/L4/L5 from the tool
- Mutating plugin manifests
- Resolving the MCP name collision with core

## Architecture

```
plugins/plugin-manager/plugin.json
tools/plugin-manager/plugin_manager.py
```

Dispatch via `TOOL_NAME` in `exec` (same B1 pattern as structural-anchor).

**Discovery:** given `root_path`,

1. Prefer `root_path/plugins/*/plugin.json`
2. Else `root_path/*/plugin.json`
3. Cap at 500 manifests; skip unreadable files

## Tool contracts

### Shared

| Field | Required | Meaning |
|-------|----------|---------|
| `root_path` | yes | Absolute path; reject `..` segments and missing paths |

Timeouts: `list_plugins` / `validate_plugin` → `5s`; `test_plugin` → `120s`.

### `list_plugins`

Input: `{ "root_path": "..." }`

Output:

```json
{
  "plugins": [
    {
      "name": "sample",
      "version": "0.1.0",
      "path": "plugins/sample/plugin.json",
      "entry_count": 1,
      "tool_count": 0
    }
  ],
  "count": 1
}
```

`path` is relative to `root_path` when under it, else absolute. Sorted by name.

### `validate_plugin`

Input: `{ "root_path": "...", "plugin": "sample" }`

Output (always exit 0 when inputs are structurally valid):

```json
{
  "ok": true,
  "plugin": "sample",
  "path": "plugins/sample/plugin.json",
  "errors": [],
  "warnings": []
}
```

Checks (aligned with `run_entry_lint.py`): name match, non-empty entries, unique entry names, valid kinds/delivery, tools have `exec` and `io_mode`, non-empty bodies. Missing plugin → `ok: false` with an error string (exit 0).

### `test_plugin`

Input: `{ "root_path": "...", "plugin": "sample", "layers": "lint" }`

- `layers` default `"lint"`: same checks as `validate_plugin` plus “has at least one entry”
- `layers: "l2"`: run `testing/contract/run_contract.py --use-repo-tools <plugin>` with cwd = `root_path` when that tree looks like this repo (has `testing/contract/run_contract.py`); otherwise error in the JSON result

Output:

```json
{
  "ok": true,
  "plugin": "sample",
  "layers": "lint",
  "errors": [],
  "output": ""
}
```

## Performance

| Tool | Target |
|------|--------|
| `list_plugins` | < 1s for ≤ 500 manifests |
| `validate_plugin` | < 1s |
| `test_plugin` (lint) | < 1s |
| `test_plugin` (l2) | bounded by tool timeout 120s |

## Failure modes

- Missing / non-dir / `..` in `root_path` → stderr + exit 1
- Missing `plugin` for validate/test → stderr + exit 1
- Malformed JSON / input > 1 MB → stderr + exit 1
- Plugin not found → exit 0, `ok: false`

## Fixture tests

- New shared fixture `plugins-mini` (tiny valid plugin tree) — justified: other fixtures are source trees, not plugin registries
- Reuse `empty`, `hostile` for empty-list / no-plugin cases
- L2 negatives: malformed JSON, missing `root_path`, nonexistent path, `..` traversal, input > 1 MB

## L5

`eval_category` is null → `l5: not-applicable` (developer tooling).

## Out of scope

Held-out eval suite. Installing into production naitv without resolving the `list_plugins` name collision.
