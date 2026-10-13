# Plugin test harness contract

Shared runners live under `testing/`. Each plugin owns only what is unique to it.
This is how ~60 plugins scale without forking the harness.

## Layout (required for any new plugin)

```
plugins/<name>/
  plugin.json          # canonical manifest (preferred over plugins/<name>.json)
  harness.json         # optional test profile (defaults apply if missing)
  tests/               # L1 (pytest / go test / bats as needed)
  README.md            # optional

tools/<name>/          # optional implementation (JSON-tool plugins)
```

Legacy `plugins/<name>.json` still loads for install, but **tests require**
`plugins/<name>/plugin.json`.

## What is shared (do not copy per plugin)

| Layer | Runner | Input it reads |
|---|---|---|
| L2 | `testing/contract/run_contract.py` | `plugin.json` + `testing/fixtures/inputs/<tool>/*.json` + `testing/contract/schemas/<tool>.schema.json` |
| L3 golden | `testing/golden/run_golden.py` | `harness.json` → `golden.queries` + `testing/golden/<plugin>/<tool>/<fixture>.json` |
| L3 perf | `testing/perf/run_perf.py` | `harness.json` → `perf` targets |
| L4 | `testing/integration/run_l4.py` | seeds tools from `plugin.json` |
| L5 | `testing/eval/run_eval.py` | tasks under `testing/eval/tasks/…`; treatment plugins from `harness.json` |
| Cross-plugin | `testing/integration/cross_plugin_check.py` | all manifests |

Fixtures under `testing/fixtures/` are **shared**. Prefer reusing `py-small` /
`go-small` / `hostile` / `empty` before adding a new fixture.

## What each plugin must add

### JSON-tool plugins (`profile: json_tools`)

1. `plugins/<name>/plugin.json` with `kind=tool` entries (`io_mode=json`, `timeout`, `exec`)
2. Implementation under `tools/<name>/` (or next to `plugin.json`)
3. Per **tool name** (global across the catalog — tool names must be unique):
   - `testing/contract/schemas/<tool>.schema.json`
   - `testing/fixtures/inputs/<tool>/` (include §3 negatives)
4. L1 tests in `plugins/<name>/tests/`
5. Optional: goldens, `harness.json` perf/L5 knobs

### Rules-only plugins (`profile: rules_only`)

Examples: `lazy-dev`. No subprocess contract.

1. `plugin.json` with rules/workflows/facts
2. `harness.json` with `"profile": "rules_only"`
3. L1: structural checks on entries (names, delivery, no duplicate tool names)
4. L2/L3/L4 skipped automatically

### Mixed plugins

`"profile": "mixed"` — L2 runs for tool entries only; rules still get entry lint.

## `harness.json` schema (optional)

```json
{
  "profile": "json_tools",
  "coverage": {
    "module": "my_plugin",
    "search_paths": ["tools/my-plugin", "plugins/my-plugin"],
    "fail_under": 80
  },
  "layers": {
    "l1": true,
    "l2": true,
    "l3_golden": true,
    "l4": true,
    "l5": false
  },
  "perf": {
    "enabled": true,
    "tool": "my_hot_tool",
    "module": "my_plugin",
    "targets_seconds": { "cold": 2.0, "warm": 0.1, "cold_start": 30.0 }
  },
  "l5": {
    "treatment_plugins": ["my-plugin"],
    "tool_names": ["my_hot_tool"]
  }
}
```

Defaults when omitted: `json_tools` if any `kind=tool` with `exec`, else `rules_only`.

## Commands

```bash
./scripts/scaffold_plugin.sh my-plugin          # directory + harness stub
./scripts/test.sh my-plugin                     # L1 → L2 → L3 golden (if present)
RUN_L4=1 ./scripts/test.sh my-plugin            # + L4
./scripts/perf.sh my-plugin                     # nightly, needs harness.perf
./scripts/eval.sh baseline|treatment            # L5 (configured plugins)
```

## Extensibility rules

1. **Never** hardcode a plugin name inside a shared runner. Read `plugin.json` / `harness.json`.
2. Tool schemas and inputs are keyed by **tool name**, not plugin name (tools are global in MCP).
3. Goldens and L1 tests are keyed by **plugin name**.
4. New fixture repos need a reason — prefer tagging an existing fixture.
5. L5 tasks declare `plugins_expected` (optional) so suites can run against subsets.
