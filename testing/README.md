# Plugin test assets

Shared L2 contract harness, frozen fixtures, and (later) golden/eval assets.

- `contract/run_contract.py` — JSON I/O contract runner (`sh -c` + stdin/stdout)
- `fixtures/` — small frozen repos and per-tool input cases
- `fixtures/generate.py` — synthetic repo builder (output not committed)

L1 unit tests live beside each plugin under `plugins/<name>/tests/`.
