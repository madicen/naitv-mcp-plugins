# Recorded baselines

Baselines are recorded **before** any treatment (plugins-on) run.

- Full run artifacts: `testing/eval/runs/` (gitignored)
- Committed summary snapshots live here so the pre-treatment bar is reviewable in PRs

Do not edit thresholds after seeing treatment results (see TEST_PLAN §6e).

## Ablation

Leave-one-out over suite `treatment_plugins` (needs `naitv-mcp` on PATH).
Stub is the default agent (CI-safe). For a real-model ablation:

```bash
AGENT=ollama OLLAMA_MODEL=qwen3:8b python3 testing/eval/run_ablation.py \
  --suite navigation --seeds 1 --agent ollama
```

Or `make l5-ablation` / `make ablation AGENT=ollama`.
