# Plugin test assets

Shared L2/L3 harness, frozen fixtures, and golden outputs.

- `contract/run_contract.py` — L2 JSON I/O contract runner (`sh -c` + stdin/stdout)
- `golden/run_golden.py` — L3 golden compare (`--update-golden` to refresh)
- `fixtures/` — small frozen repos and per-tool input cases
- `fixtures/generate.py` — synthetic repo builder (output not committed)

L1 unit tests live beside each plugin under `plugins/<name>/tests/`.
Run `./scripts/test.sh <plugin>` for L1 → L2 → L3 (when goldens exist).
