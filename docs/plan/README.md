# naitv-mcp plugin plan (v2)

This folder is the working plan for building the plugin catalog. It replaces the earlier planning set, which predates the current repo.

## What is here

| File | Purpose |
|---|---|
| `VCS.md` | jj-only version control rules for agents, commit format, PR format |
| `ARCHITECTURE.md` | how plugins actually work in this repo (entries, `io_mode`, `exec`, profiles) |
| `TESTING.md` | per-plugin test requirements, and how we prove a plugin helps a small local model |
| `CYCLE_PROMPT.md` | the Cursor prompt that builds one plugin at a time, then commits, pushes, and opens a PR |
| `plugins.json` | the catalog: build order, status, tools, dependencies, eval category |
| `PLUGIN_REFERENCE_MATRIX.md` | the source matrix, as supplied (64 plugin rows, plus core and templates) |
| `MATRIX_NOTES.md` | how the matrix was converted, and every normalization or anomaly |
| `../../scripts/catalog_check.py` | validates `plugins.json` |
| `archive/` | superseded planning docs, kept for history |

Authority for the harness mechanics is `testing/PLUGIN_HARNESS.md`. Authority for requirements is `TESTING.md`. Where they disagree, fix the disagreement in the same change.

## Status

- Catalog: 66 entries. That is the 64 plugin rows from the matrix, plus `lazy-dev` and `loop-engineering-go`, which predate it. 4 exist. 1 is ready to build (`plugin-manager`). 61 need specs.
- The matrix gives tool counts and performance targets but not tool names. Each `needs-spec` entry gets a spec PR first (CYCLE_PROMPT step 2b), and a person approves it before it is built.
- The matrix's core row and three template rows are excluded. Templates are replaced by `scripts/scaffold_plugin.sh`. See `MATRIX_NOTES.md` for the full list of normalizations and anomalies.
- L5: no plugin has a measured uplift result yet. The existing navigation numbers were produced with the stub agent and are not evidence.

## How to run

1. Open naitv-mcp-plugins in Cursor (auto mode).
2. Paste `CYCLE_PROMPT.md`. To limit scope to one plugin, put `PLUGIN=<name>` on the first line.
3. Read the final report. Review each PR. Merge when CI is green and the L5 result is recorded honestly.

## Decisions still needed

1. ~~The reference local model for L5~~ **Decided:** `qwen3:8b` via Ollama (`l5.model` in each `harness.json`; `OLLAMA_MODEL=qwen3:8b`). L5 stays `pending` until measured with `AGENT=ollama`.
2. Who writes and owns the held-out suite. The cycle never touches it.
3. Whether `lint-fix-loop` and similar tools may call external linters and test runners. That decides which tools need the timeout and fixture rules tightened.
4. Confirm the ambiguous dependency names and phase-order exceptions listed in `MATRIX_NOTES.md`.
