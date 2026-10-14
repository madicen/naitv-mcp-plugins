# plugin-manager Implementation Plan

**Goal:** Ship the Phase 1 `plugin-manager` plugin: list / validate / test plugin manifests under a filesystem root.

**Architecture:** One Python stdlib script dispatches on `TOOL_NAME`. Manifest discovery under `root_path`. Lint checks mirror `testing/contract/run_entry_lint.py`. Optional L2 shell-out for `test_plugin`.

**Tech Stack:** Python 3 stdlib, naitv-mcp `io_mode=json`, pytest for L1.

**Spec:** `docs/superpowers/specs/2026-10-14-plugin-manager-design.md`

## File map

| Path | Responsibility |
|------|----------------|
| `tools/plugin-manager/plugin_manager.py` | CLI, discovery, lint, L2 shell-out |
| `plugins/plugin-manager/plugin.json` | Three tool entries |
| `plugins/plugin-manager/harness.json` | json_tools profile, golden, L4 |
| `plugins/plugin-manager/tests/test_unit.py` | L1 per tool + error paths |
| `testing/fixtures/plugins-mini/` | Tiny registry fixture |
| `testing/contract/schemas/{list,validate,test}_plugin*.schema.json` | L2 schemas |
| `testing/fixtures/inputs/<tool>/` | L2 inputs including negatives |
| `testing/golden/plugin-manager/...` | L3 goldens |
| `registry.json` | Register plugin |
| `docs/plan/plugins.json` | status → exists |

## Tasks

### Task 1: Scaffold + fixture

- [ ] `./scripts/scaffold_plugin.sh plugin-manager json_tools`
- [ ] Create `testing/fixtures/plugins-mini/plugins/sample/plugin.json`

### Task 2: Implement tools

- [ ] `tools/plugin-manager/plugin_manager.py` with three handlers
- [ ] Fill `plugins/plugin-manager/plugin.json` entries

### Task 3: L1–L4 harness pieces

- [ ] Schemas + input fixtures for all three tools
- [ ] Unit tests
- [ ] harness.json golden queries + L4 smoke
- [ ] Generate goldens with `--update-golden`

### Task 4: Wire catalog

- [ ] `registry.json` entry
- [ ] `docs/plan/plugins.json` → `exists`, `l5: not-applicable`
- [ ] `python3 scripts/catalog_check.py`

### Task 5: Verify

- [ ] `make test-plugin PLUGIN=plugin-manager`
- [ ] `make l4 PLUGIN=plugin-manager`
- [ ] Describe, bookmark, push, open PR
