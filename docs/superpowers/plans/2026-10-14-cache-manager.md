# cache-manager implementation plan

**Goal:** Namespaced SQLite cache tools under `~/.cache/naitv-mcp/cache-manager/`.

## Tasks

1. Implement `tools/cache-manager/cache_manager.py` (get/put/stats/prune).
2. `plugin.json` + `harness.json` + unit tests.
3. Contract schemas/inputs; golden for empty/py-small (get-before-put order).
4. L5 not-applicable; catalog `exists`; registry; PR.
