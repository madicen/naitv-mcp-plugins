# naitv-mcp plugin architecture (as built)

Status: current. Replaces the Plugin-interface design in `archive/PHASE1_CORRECTED.md` and `archive/PLUGIN_TEMPLATE_CORRECTED.md`, which were written before the repo was inspected. Those files are kept for history only.

## 1. The model

- naitv-mcp core is generic. It loads plugin entries, serves MCP tools, and runs executables.
- A plugin is a directory `plugins/<name>/` with `plugin.json`. The manifest holds `entries`, each with a `kind`:
  - `rule`: text delivered to the agent (`delivery: "init"` or `"on-demand"`).
  - `tool`: an MCP tool backed by an executable.
- Tool entries carry `fields`: `exec`, `io_mode`, `timeout`, `params`. `params` is a JSON array string describing inputs.
- JSON I/O is already in core (Phase 1 is done). A tool with `io_mode: "json"` receives one JSON object on stdin and returns one JSON object on stdout.
- `exec` sets the tool name for multi-tool scripts with an inline env var. Example from `structural-anchor`:

  `TOOL_NAME=get_project_map python3 ~/.config/naitv-mcp/tools/structural-anchor/structural_anchor.py`

- Implementation lives in `tools/<name>/`. Tests and harness config live in `plugins/<name>/`.
- `registry.json` lists each plugin's install URL (`plugins/<name>/plugin.json` on `main`).
- Tool names are global across the catalog. Two plugins may not register the same tool name.
- Human review gates activation. A new entry is not offered to users until it is approved.

There is no `Plugin` interface, no `CallTool`/`Execution()` method, and no separate subprocess host. Do not add them.

## 2. Profiles

| Profile | Use for | Layers |
|---|---|---|
| `json_tools` | executables with JSON I/O | L1 to L5 |
| `rules_only` | rules, workflows, facts | L1 structural checks only (L5 optional) |
| `mixed` | rules plus text-mode tools (`working_dir`, no `io_mode=json`) | L1 and L3 golden; L2/L4 only for json tools |

Profile defaults are described in `testing/PLUGIN_HARNESS.md`.

## 3. Rules for every tool

- Output is exactly one JSON line on stdout. Diagnostics go to stderr. Partial output is never written.
- Deterministic: the same input and repo state give byte-identical output, apart from declared volatile fields such as `cached`.
- Bounded: stdout at most 1 MB. Traversal depth and file counts are capped, and the caps are documented.
- Stdlib first. Add a dependency only when the plugin cannot work without it, and list it in the README.
- Caches live only under `~/.cache/naitv-mcp/<plugin>/`. Nothing else is written.
- No network access unless the plugin's spec explicitly says so, and then the spec must justify it. The contract forbids implicit network use.
- Declare an honest `timeout`. The harness checks that it is enforced.
- Validate every input and return a structured error for bad input. Do not crash with a traceback on stdout.

## 4. Per-plugin workflow (superpowers convention)

Each plugin goes through the same steps, and the artifacts stay in the repo:

1. Spec: `docs/superpowers/specs/<YYYY-MM-DD>-<name>-design.md`. Purpose, tools with input and output JSON, performance target, failure modes, out of scope.
2. Plan: `docs/superpowers/plans/<YYYY-MM-DD>-<name>.md`. Ordered tasks with file paths.
3. Scaffold: `./scripts/scaffold_plugin.sh <name> <profile>`.
4. Implement tools and entries.
5. Tests per `TESTING.md` section 2.
6. L5 proof per `TESTING.md` section 3.
7. Catalog update in `docs/plan/plugins.json`, then `python3 scripts/catalog_check.py`.

The existing `structural-anchor` and `symbol-navigator` specs and plans are the reference examples.

## 5. Catalog

`docs/plan/plugins.json` is the build order: 66 entries, built from `PLUGIN_REFERENCE_MATRIX.md` (64 plugin rows) plus two repo plugins that predate it. Four exist, one is `planned` (`plugin-manager`), and 61 are `needs-spec`. The matrix gives tool counts but not tool names, so each `needs-spec` entry gets a spec PR before it can be built. The cycle never builds a `needs-spec` entry directly. `MATRIX_NOTES.md` records how the matrix was converted.
