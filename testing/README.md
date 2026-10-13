# Plugin test assets

Shared L2/L3 harness, frozen fixtures, and golden outputs.

- `contract/run_contract.py` — L2 JSON I/O contract runner (`sh -c` + stdin/stdout)
- `golden/run_golden.py` — L3 golden compare (`--update-golden` to refresh)
- `perf/run_perf.py` — L3 perf (cold/warm p50/p95 on generated-50k; nightly)
- `integration/` — L4 MCP tests via `naitv-mcp serve` (stdio JSON-RPC)
- `eval/` — L5 uplift eval (tasks, graders, runner); `runs/` gitignored
- `fixtures/` — small frozen repos and per-tool input cases
- `fixtures/generate.py` — synthetic repo builder (output not committed)

L1 unit tests live beside each plugin under `plugins/<name>/tests/`.
Run `./scripts/test.sh <plugin>` for L1 → L2 → L3 golden (when goldens exist).
Run `./scripts/perf.sh structural-anchor` for the nightly 50k perf gate
(or `RUN_PERF=1 pytest -m perf` for a small smoke).
Run `./scripts/l4.sh structural-anchor` (or `RUN_L4=1 ./scripts/test.sh …`) for MCP
integration; requires `naitv-mcp` on PATH.
L5: `./scripts/eval.sh baseline` **before** any treatment run; then
`./scripts/eval.sh treatment` (stub uses MCP tools under treatment).
`AGENT=ollama OLLAMA_MODEL=qwen3:8b ./scripts/eval.sh treatment` for a real model
tool-loop. Compare: `python3 testing/eval/compare_eval.py`.
