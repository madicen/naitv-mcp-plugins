# Perf hardware identity

Release-gate L3 numbers must come from a **fixed runner**, not a laptop.

## Required env

| Variable | Purpose |
|---|---|
| `PERF_RUNNER_ID` | Stable label written into every perf JSON report (e.g. `nightly-m2-mini`) |
| `PERF_RUNS_ON` (GitHub Actions repo variable) | Optional `runs-on` override for `.github/workflows/nightly.yml` (self-hosted label or larger runner) |

Laptop / ad-hoc results without `PERF_RUNNER_ID` are fine for local iteration but **inadmissible** for certification or release gates.

## Nightly

The nightly workflow sets `PERF_RUNNER_ID` from `vars.PERF_RUNNER_ID` when present, otherwise `runner-${{ runner.name }}`. Point a self-hosted runner at the repo and set `PERF_RUNS_ON` / `PERF_RUNNER_ID` in repository variables when ready.
