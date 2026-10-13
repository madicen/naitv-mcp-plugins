#!/usr/bin/env python3
"""L5 uplift eval harness (navigation suite).

Conditions:
  baseline  — no plugin tools
  treatment — suite treatment_plugins via naitv-mcp MCP (navigation: structural-anchor + symbol-navigator)

Agents:
  stub   — deterministic; uses MCP tools under treatment
  ollama — local model; function-calling tool loop under treatment
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_ROOT = Path(__file__).resolve().parent
TASKS_ROOT = EVAL_ROOT / "tasks"
RUNS_ROOT = EVAL_ROOT / "runs"
FIXTURES = REPO_ROOT / "testing" / "fixtures"

sys.path.insert(0, str(EVAL_ROOT))

from graders.criteria import grade_success  # noqa: E402
from graders.hallucination import grade_hallucination  # noqa: E402
from mcp_session import mcp_session  # noqa: E402
from tool_loop import ollama_with_mcp, toolstub_with_mcp  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "testing"))
from plugin_harness import load_harness  # noqa: E402


def treatment_plugins_for(suite: str) -> list[str]:
    """Resolve treatment plugins: suite.json first, else primary plugin harness.l5."""
    meta_path = TASKS_ROOT / suite / "suite.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        plugins = meta.get("treatment_plugins")
        if plugins:
            return list(plugins)
    primary = {
        "navigation": "structural-anchor",
    }.get(suite, "structural-anchor")
    try:
        h = load_harness(primary)
    except FileNotFoundError:
        return [primary]
    return list((h.get("l5") or {}).get("treatment_plugins") or [primary])



def task_dir(suite: str, version: int, *, held_out: bool = False) -> Path:
    if held_out:
        return TASKS_ROOT / suite / "held-out" / f"v{version}"
    return TASKS_ROOT / suite / f"v{version}"


def load_tasks(suite: str, version: int, *, held_out: bool = False) -> list[dict[str, Any]]:
    directory = task_dir(suite, version, held_out=held_out)
    if not directory.is_dir():
        raise SystemExit(f"missing task suite: {directory}")
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.json"))
    ]


def project_map_for(fixture: str) -> dict[str, Any]:
    tools = REPO_ROOT / "tools" / "structural-anchor"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import structural_anchor as sa  # type: ignore

    root = (FIXTURES / fixture).resolve()
    return sa.get_project_map(root, 3, set(sa.DEFAULT_SKIP_DIRS))


def stub_baseline(task: dict[str, Any]) -> dict[str, Any]:
    if task.get("control"):
        text = (
            "The add function in pkg/greeter.py returns the sum of its two integer arguments."
        )
    elif task["id"].startswith("nav-001"):
        text = "I am not sure where Greeter lives without searching the tree."
    elif task["id"].startswith("nav-002"):
        text = "This project seems to contain some source files."
    elif task["id"].startswith("nav-004"):
        text = "I do not know which symbols match that pattern."
    else:
        text = "I do not know the package layout."
    return {
        "final_answer": text,
        "turns": 1,
        "tool_calls": [],
        "agent": "stub",
        "condition": "baseline",
    }


def run_task(
    task: dict[str, Any],
    *,
    condition: str,
    agent: str,
    seed: int,
    client: Any,
    plugins: list[str] | None = None,
) -> dict[str, Any]:
    import time

    t0 = time.perf_counter()
    if agent == "stub":
        if condition == "treatment":
            trajectory = toolstub_with_mcp(
                client, task, condition=condition, plugins=plugins or []
            )
        else:
            trajectory = stub_baseline(task)
    elif agent == "ollama":
        trajectory = ollama_with_mcp(
            client if condition == "treatment" else None,
            task,
            condition=condition,
            seed=seed,
            plugins=plugins or [],
        )
    else:
        raise SystemExit(f"unknown agent {agent!r}")

    answer = trajectory.get("final_answer") or ""
    success = grade_success(answer, task.get("success") or {})
    try:
        pmap = project_map_for(task["fixture"])
        hallu = grade_hallucination(answer, pmap)
    except Exception as exc:  # pragma: no cover
        hallu = {"error": str(exc), "nonexistent_rate": None, "nonexistent": []}

    return {
        "task_id": task["id"],
        "suite": task.get("suite"),
        "category": task.get("category"),
        "control": bool(task.get("control")),
        "fixture": task["fixture"],
        "condition": condition,
        "seed": seed,
        "success": success,
        "hallucination": hallu,
        "trajectory": trajectory,
        "wall_seconds": time.perf_counter() - t0,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(results)
    successes = [r for r in results if r.get("success", {}).get("passed")]
    controls = [r for r in results if r.get("control")]
    control_ok = [r for r in controls if r.get("success", {}).get("passed")]
    rates = [
        r.get("hallucination", {}).get("nonexistent_rate")
        for r in results
        if r.get("hallucination", {}).get("nonexistent_rate") is not None
    ]
    tool_n = sum(len(r.get("trajectory", {}).get("tool_calls") or []) for r in results)
    return {
        "n": n,
        "success_rate": (len(successes) / n) if n else 0.0,
        "control_n": len(controls),
        "control_success_rate": (len(control_ok) / len(controls)) if controls else None,
        "mean_nonexistent_symbol_rate": (sum(rates) / len(rates)) if rates else None,
        "mean_wall_seconds": (
            sum(r.get("wall_seconds", 0) for r in results) / n if n else 0.0
        ),
        "total_tool_calls": tool_n,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="navigation")
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument(
        "--condition", choices=("baseline", "treatment"), default="baseline"
    )
    parser.add_argument("--agent", choices=("stub", "ollama"), default="stub")
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--seed-base", type=int, default=42)
    parser.add_argument("--label", default="")
    parser.add_argument(
        "--held-out",
        action="store_true",
        help="load tasks/<suite>/held-out/v<version>/ instead of tasks/<suite>/v<version>/",
    )
    args = parser.parse_args()

    if args.condition == "treatment" and shutil.which("naitv-mcp") is None:
        raise SystemExit("naitv-mcp required on PATH for treatment condition")

    tasks = load_tasks(args.suite, args.version, held_out=args.held_out)
    rng = random.Random(args.seed_base)
    order = list(tasks)
    rng.shuffle(order)

    plugins = treatment_plugins_for(args.suite) if args.condition == "treatment" else []
    results: list[dict[str, Any]] = []

    # One MCP server for the whole run (treatment); baseline needs no plugin server.
    if args.condition == "treatment":
        with mcp_session(plugins=plugins) as client:
            for task in order:
                for i in range(args.seeds):
                    results.append(
                        run_task(
                            task,
                            condition=args.condition,
                            agent=args.agent,
                            seed=args.seed_base + i,
                            client=client,
                            plugins=plugins,
                        )
                    )
    else:
        for task in order:
            for i in range(args.seeds):
                results.append(
                    run_task(
                        task,
                        condition=args.condition,
                        agent=args.agent,
                        seed=args.seed_base + i,
                        client=None,
                    )
                )

    summary = summarize(results)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = args.label or args.condition
    if args.held_out:
        label = f"heldout-{label}"
    out_dir = RUNS_ROOT / f"{args.suite}-v{args.version}-{label}-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "schema_version": 1,
        "suite": args.suite,
        "suite_version": args.version,
        "condition": args.condition,
        "plugins": plugins,
        "agent": args.agent,
        "model": os.environ.get("OLLAMA_MODEL", "qwen3:8b")
        if args.agent == "ollama"
        else None,
        "seeds": args.seeds,
        "seed_base": args.seed_base,
        "held_out": args.held_out,
        "thresholds_preregistered": {
            "helps_success_pp": 10,
            "harmful_control_drop_pp": 2,
            "helps_hallucination_relative_drop": 0.30,
        },
        "summary": summary,
        "results": results,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "naitv_mcp_version": "naitv-mcp:present"
        if shutil.which("naitv-mcp")
        else None,
        "hardware": {"platform": sys.platform, "python": sys.version.split()[0]},
    }
    (out_dir / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    latest_name = (
        f"{args.suite}-v{args.version}-heldout-{args.condition}-latest.json"
        if args.held_out
        else f"{args.suite}-v{args.version}-{args.condition}-latest.json"
    )
    latest = RUNS_ROOT / latest_name
    latest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.condition == "baseline" and not args.held_out and args.suite == "navigation":
        pointer = RUNS_ROOT / "BASELINE_NAVIGATION_V1.json"
        pointer.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        snap = {
            "recorded_at": report["recorded_at"],
            "suite": report["suite"],
            "suite_version": report["suite_version"],
            "condition": "baseline",
            "plugins": [],
            "agent": report["agent"],
            "model": report["model"],
            "seeds": report["seeds"],
            "thresholds_preregistered": report["thresholds_preregistered"],
            "summary": summary,
            "task_ids": [t["id"] for t in tasks],
            "full_report": str(out_dir / "report.json"),
        }
        snap_path = EVAL_ROOT / "baselines" / "navigation-v1-baseline.json"
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        snap_path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote baseline pointer {pointer}")
        print(f"Wrote committed snapshot {snap_path}")

    if args.condition == "treatment" and not args.held_out and args.suite == "navigation":
        treat_ptr = RUNS_ROOT / "TREATMENT_NAVIGATION_V1.json"
        treat_ptr.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote treatment pointer {treat_ptr}")

    print(json.dumps(summary, indent=2))
    print(f"Wrote {out_dir / 'report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
