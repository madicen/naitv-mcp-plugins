#!/usr/bin/env python3
"""Run per-plugin L5 baseline+treatment with Ollama and update the catalog.

Usage:
  python3 scripts/run_l5_measurements.py              # all pending plugins
  python3 scripts/run_l5_measurements.py --limit 3    # first N
  python3 scripts/run_l5_measurements.py --plugin workspace-search
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs" / "plan" / "plugins.json"
BASELINES = ROOT / "testing" / "eval" / "baselines"
RUNS = ROOT / "testing" / "eval" / "runs"


def load_catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def tagged_task_counts(version: int = 1) -> dict[str, int]:
    from collections import Counter
    c: Counter[str] = Counter()
    for path in (ROOT / "testing" / "eval" / "tasks").glob(f"*/v{version}/*.json"):
        t = json.loads(path.read_text(encoding="utf-8"))
        for pl in t.get("plugins_expected") or []:
            c[pl] += 1
    return dict(c)


def pending_plugins(
    catalog: dict,
    *,
    only: str | None,
    min_tagged: int = 5,
    version: int = 1,
    remeasure: bool = False,
) -> list[dict]:
    counts = tagged_task_counts(version)
    out = []
    for p in sorted(catalog["plugins"], key=lambda x: x.get("order", 999)):
        if p.get("status") != "exists":
            continue
        if only and p["name"] != only:
            continue
        # Explicit --plugin (or --remeasure) may re-run measured plugins on a new suite version.
        if not only and not remeasure and p.get("l5") != "pending":
            continue
        if not p.get("eval_category"):
            continue
        if counts.get(p["name"], 0) < min_tagged:
            print(f"skip {p['name']}: only {counts.get(p['name'], 0)} tagged v{version} tasks")
            continue
        out.append(p)
    return out


def gate_from_harness(name: str) -> dict:
    path = ROOT / "plugins" / name / "harness.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict((data.get("l5") or {}).get("gate") or {})


def run_arm(plugin: str, suite: str, condition: str, seeds: int, version: int) -> Path:
    env = os.environ.copy()
    env["OLLAMA_MODEL"] = env.get("OLLAMA_MODEL", "qwen3:8b")
    env["OLLAMA_HOST"] = env.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    cmd = [
        sys.executable,
        str(ROOT / "testing" / "eval" / "run_eval.py"),
        "--suite",
        suite,
        "--version",
        str(version),
        "--condition",
        condition,
        "--agent",
        "ollama",
        "--seeds",
        str(seeds),
        "--plugin",
        plugin,
    ]
    print(f"\n>>> {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=str(ROOT), env=env, check=True)
    # latest pointer written by run_eval
    latest = RUNS / f"{suite}-v{version}-{plugin}-{condition}-latest.json"
    if not latest.is_file():
        raise SystemExit(f"missing latest report {latest}")
    return latest


def evaluate_gate(baseline: dict, treatment: dict, gate: dict) -> dict:
    bs = baseline.get("summary") or {}
    ts = treatment.get("summary") or {}
    b_rate = float(bs.get("success_rate") or 0)
    t_rate = float(ts.get("success_rate") or 0)
    delta_pp = (t_rate - b_rate) * 100
    b_ctrl = bs.get("control_success_rate")
    t_ctrl = ts.get("control_success_rate")
    ctrl_drop_pp = None
    if b_ctrl is not None and t_ctrl is not None:
        ctrl_drop_pp = (float(b_ctrl) - float(t_ctrl)) * 100
    b_tools = int(bs.get("total_tool_calls") or 0)
    t_tools = int(ts.get("total_tool_calls") or 0)
    # Baseline is core-only (no plugin tools), so tool_calls==0 by design.
    # Inflation vs that baseline is undefined; skip unless baseline used tools.
    tool_infl_pct = None
    if b_tools > 0:
        tool_infl_pct = ((t_tools - b_tools) / b_tools) * 100

    b_hall = bs.get("mean_nonexistent_symbol_rate")
    t_hall = ts.get("mean_nonexistent_symbol_rate")
    hall_increase = None
    if b_hall is not None and t_hall is not None:
        hall_increase = float(t_hall) - float(b_hall)

    min_delta = float(gate.get("min_success_delta_pp", 10))
    max_ctrl = float(gate.get("max_control_regression_pp", 2))
    max_infl = float(gate.get("max_tool_call_inflation_pct", 25))
    max_hall_inc = float(gate.get("max_nonexistent_symbol_rate_increase", 0))
    ci_excl_zero = bool(gate.get("ci_must_exclude_zero", True))

    helps = delta_pp >= min_delta
    if ci_excl_zero and not (delta_pp > 0):
        helps = False
    harmful_ctrl = ctrl_drop_pp is not None and ctrl_drop_pp > max_ctrl
    harmful_tools = tool_infl_pct is not None and tool_infl_pct > max_infl
    harmful_hall = hall_increase is not None and hall_increase > max_hall_inc + 1e-12
    passed = helps and not harmful_ctrl and not harmful_tools and not harmful_hall
    return {
        "baseline_success_rate": b_rate,
        "treatment_success_rate": t_rate,
        "delta_pp": delta_pp,
        "control_drop_pp": ctrl_drop_pp,
        "tool_inflation_pct": tool_infl_pct,
        "nonexistent_rate_increase": hall_increase,
        "gate": gate,
        "passed": passed,
        "l5": "measured-helpful" if passed else "measured-no-uplift",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--plugin", default="", help="single plugin (remeasures even if not pending)")
    ap.add_argument("--plugins", default="", help="comma-separated plugin names to remeasure")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--version", type=int, default=1, help="task suite version (writes *-vN.json baselines)")
    ap.add_argument("--remeasure", action="store_true", help="include already-measured plugins")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    catalog = load_catalog()
    names = [x.strip() for x in args.plugins.split(",") if x.strip()]
    if args.plugin:
        names = [args.plugin]
    if names:
        by = {p["name"]: p for p in catalog["plugins"]}
        plugins = []
        counts = tagged_task_counts(args.version)
        for n in names:
            p = by.get(n)
            if not p:
                raise SystemExit(f"unknown plugin {n}")
            if counts.get(n, 0) < 1:
                print(f"skip {n}: no tagged v{args.version} tasks")
                continue
            plugins.append(p)
    else:
        plugins = pending_plugins(
            catalog,
            only=None,
            min_tagged=5,
            version=args.version,
            remeasure=args.remeasure,
        )
    if args.limit:
        plugins = plugins[: args.limit]
    if not plugins:
        print("no pending plugins to measure")
        return 0

    print(
        f"measuring {len(plugins)} plugins with OLLAMA_MODEL={os.environ.get('OLLAMA_MODEL', 'qwen3:8b')} "
        f"seeds={args.seeds} version={args.version}"
    )
    results_log = []

    by_name = {p["name"]: p for p in catalog["plugins"]}
    for p in plugins:
        name = p["name"]
        suite = p["eval_category"]
        print(f"\n======== {name} suite={suite} v{args.version} ========", flush=True)
        if args.dry_run:
            results_log.append({"name": name, "dry_run": True})
            continue
        gate = gate_from_harness(name)
        b_path = run_arm(name, suite, "baseline", args.seeds, args.version)
        t_path = run_arm(name, suite, "treatment", args.seeds, args.version)
        baseline = json.loads(b_path.read_text(encoding="utf-8"))
        treatment = json.loads(t_path.read_text(encoding="utf-8"))
        verdict = evaluate_gate(baseline, treatment, gate)
        snap = {
            "plugin": name,
            "suite": suite,
            "version": args.version,
            "model": treatment.get("model"),
            "agent": "ollama",
            "seeds": args.seeds,
            "baseline_summary": baseline.get("summary"),
            "treatment_summary": treatment.get("summary"),
            "verdict": verdict,
            "baseline_report": str(b_path),
            "treatment_report": str(t_path),
        }
        BASELINES.mkdir(parents=True, exist_ok=True)
        snap_path = BASELINES / f"{name}-{suite}-v{args.version}.json"
        snap_path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
        entry = by_name[name]
        entry["l5"] = verdict["l5"]
        notes = entry.get("notes") or ""
        note_bit = (
            f" L5 v{args.version} {verdict['l5']} (qwen3:8b, seeds={args.seeds}, "
            f"Δ={verdict['delta_pp']:.1f}pp)."
        )
        entry["notes"] = (notes + note_bit).strip()
        CATALOG.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(verdict, indent=2), flush=True)
        print(f"Wrote {snap_path}", flush=True)
        results_log.append({"name": name, "version": args.version, **verdict})

    summary_path = RUNS / f"l5-measurement-summary-v{args.version}.json"
    RUNS.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(results_log, indent=2) + "\n", encoding="utf-8")
    print(f"\nDone. Summary: {summary_path}")
    helpful = sum(1 for r in results_log if r.get("l5") == "measured-helpful")
    no_up = sum(1 for r in results_log if r.get("l5") == "measured-no-uplift")
    print(f"measured-helpful={helpful} measured-no-uplift={no_up}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
