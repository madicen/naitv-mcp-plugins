# dependency-graph-analyzer implementation plan

> **For agentic workers:** Implement tools under `tools/dependency-graph-analyzer/`, wire `plugins/dependency-graph-analyzer/`, L1–L4 harness assets, navigation L5 tasks. Do not touch held-out eval.

**Goal:** Python/Go import graph build/query/hubs/export for agents.

**Architecture:** One Python module, `TOOL_NAME` dispatch, JSON stdin/stdout.

## Tasks

1. Implement `dependency_graph_analyzer.py` (build/query/hubs/export).
2. `plugin.json` + `harness.json` + unit/manifest tests.
3. Contract schemas + inputs; golden for deps-mini/empty/go-small.
4. Navigation L5: 10 treatment + 2 control tasks; gate in harness; `l5=pending` without model.
5. Catalog `exists`, registry entry, jj bookmark + PR.
