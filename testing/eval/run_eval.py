#!/usr/bin/env python3
"""L5 uplift eval harness (navigation suite skeleton).

Conditions:
  baseline  — core naitv-mcp tools only (no structural-anchor plugin tools)
  treatment — core + structural-anchor plugin tools

Agents:
  stub   — deterministic no-tool / weak answers (harness smoke + schema baseline)
  ollama — optional local chat model via OLLAMA_HOST / OLLAMA_MODEL

Record a baseline before enabling treatment. Results land in testing/eval/runs/
(gitignored).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_ROOT = Path(__file__).resolve().parent
TASKS_ROOT = EVAL_ROOT / "tasks"
RUNS_ROOT = EVAL_ROOT / "runs"
FIXTURES = REPO_ROOT / "testing" / "fixtures"
INTEGRATION = REPO_ROOT / "testing" / "integration"

sys.path.insert(0, str(EVAL_ROOT))
sys.path.insert(0, str(INTEGRATION))

from graders.criteria import grade_success  # noqa: E402
from graders.hallucination import grade_hallucination  # noqa: E402


def load_tasks(suite: str, version: int) -> list[dict[str, Any]]:
    directory = TASKS_ROOT / suite / f"v{version}"
    if not directory.is_dir():
        raise SystemExit(f"missing task suite: {directory}")
    tasks = []
    for path in sorted(directory.glob("*.json")):
        tasks.append(json.loads(path.read_text(encoding="utf-8")))
    return tasks


def project_map_for(fixture: str) -> dict[str, Any]:
    """Ground-truth map via in-process structural-anchor (grader only)."""
    tools = REPO_ROOT / "tools" / "structural-anchor"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import structural_anchor as sa  # type: ignore

    root = (FIXTURES / fixture).resolve()
    return sa.get_project_map(root, 3, set(sa.DEFAULT_SKIP_DIRS))


def stub_answer(task: dict[str, Any], *, condition: str) -> dict[str, Any]:
    """Weak deterministic agent: no tools. Baseline-like behavior."""
    # Intentionally incomplete for navigation tasks; control task can pass.
    if task.get("control"):
        text = (
            "The add function in pkg/greeter.py returns the sum of its two integer arguments."
        )
    elif task["id"].startswith("nav-001"):
        text = "I am not sure where Greeter lives without searching the tree."
    elif task["id"].startswith("nav-002"):
        text = "This project seems to contain some source files."
    else:
        text = "I do not know the package layout."
    return {
        "final_answer": text,
        "turns": 1,
        "tool_calls": [],
        "agent": "stub",
        "condition": condition,
    }


def ollama_chat(prompt: str, *, model: str, host: str, seed: int) -> str:
    payload = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0, "seed": seed},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a careful coding assistant. Answer briefly. "
                    "Only name symbols that exist in the project. "
                    "If unsure, say you are unsure."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    return str(data.get("message", {}).get("content", ""))


def ollama_answer(task: dict[str, Any], *, condition: str, seed: int) -> dict[str, Any]:
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    fixture_root = FIXTURES / task["fixture"]
    prompt = (
        f"Fixture repo root: {fixture_root}\n"
        f"Condition: {condition} (plugins={'off' if condition == 'baseline' else 'on'})\n\n"
        f"Task: {task['request']}\n"
    )
    # Skeleton: ollama path is chat-only (no tool loop yet). Treatment tool-loop is next.
    try:
        text = ollama_chat(prompt, model=model, host=host, seed=seed)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "final_answer": "",
            "turns": 0,
            "tool_calls": [],
            "agent": "ollama",
            "model": model,
            "error": str(exc),
            "condition": condition,
        }
    return {
        "final_answer": text,
        "turns": 1,
        "tool_calls": [],
        "agent": "ollama",
        "model": model,
        "condition": condition,
    }


def run_task(
    task: dict[str, Any],
    *,
    condition: str,
    agent: str,
    seed: int,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    if agent == "stub":
        trajectory = stub_answer(task, condition=condition)
    elif agent == "ollama":
        trajectory = ollama_answer(task, condition=condition, seed=seed)
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
    return {
        "n": n,
        "success_rate": (len(successes) / n) if n else 0.0,
        "control_n": len(controls),
        "control_success_rate": (len(control_ok) / len(controls)) if controls else None,
        "mean_nonexistent_symbol_rate": (sum(rates) / len(rates)) if rates else None,
        "mean_wall_seconds": (
            sum(r.get("wall_seconds", 0) for r in results) / n if n else 0.0
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="navigation")
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument(
        "--condition",
        choices=("baseline", "treatment"),
        default="baseline",
        help="baseline = plugins off (required first)",
    )
    parser.add_argument(
        "--agent",
        choices=("stub", "ollama"),
        default="stub",
        help="stub for harness/schema; ollama when a local model is available",
    )
    parser.add_argument("--seeds", type=int, default=3, help="runs per task (plan: 3)")
    parser.add_argument("--seed-base", type=int, default=42)
    parser.add_argument(
        "--label",
        default="",
        help="optional label included in the run directory name",
    )
    args = parser.parse_args()

    if args.condition == "treatment" and args.agent == "stub":
        print(
            "note: stub agent ignores treatment tools; use --agent ollama "
            "once the tool loop lands",
            file=sys.stderr,
        )

    tasks = load_tasks(args.suite, args.version)
    # Randomize task order (tool-order randomization is for MCP treatment later).
    rng = random.Random(args.seed_base)
    order = list(tasks)
    rng.shuffle(order)

    results: list[dict[str, Any]] = []
    for task in order:
        for i in range(args.seeds):
            seed = args.seed_base + i
            results.append(
                run_task(task, condition=args.condition, agent=args.agent, seed=seed)
            )

    summary = summarize(results)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = args.label or args.condition
    out_dir = RUNS_ROOT / f"{args.suite}-v{args.version}-{label}-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "schema_version": 1,
        "suite": args.suite,
        "suite_version": args.version,
        "condition": args.condition,
        "plugins": []
        if args.condition == "baseline"
        else ["structural-anchor"],
        "agent": args.agent,
        "model": os.environ.get("OLLAMA_MODEL") if args.agent == "ollama" else None,
        "seeds": args.seeds,
        "seed_base": args.seed_base,
        "thresholds_preregistered": {
            "helps_success_pp": 10,
            "harmful_control_drop_pp": 2,
            "helps_hallucination_relative_drop": 0.30,
        },
        "started_note": (
            "Baseline must be recorded before treatment. "
            "Do not reinterpret thresholds after seeing results."
        ),
        "summary": summary,
        "results": results,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "naitv_mcp_version": _naitv_version(),
        "hardware": {
            "platform": sys.platform,
            "python": sys.version.split()[0],
        },
    }
    (out_dir / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    latest = RUNS_ROOT / f"{args.suite}-v{args.version}-{args.condition}-latest.json"
    latest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    # Stable pointer for "the" baseline recorded before treatment.
    if args.condition == "baseline":
        pointer = RUNS_ROOT / "BASELINE_NAVIGATION_V1.json"
        pointer.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote baseline pointer {pointer}")
        # Committed snapshot (summary only) so pre-treatment bar is reviewable.
        baselines = EVAL_ROOT / "baselines"
        baselines.mkdir(parents=True, exist_ok=True)
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
        snap_path = baselines / "navigation-v1-baseline.json"
        snap_path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote committed snapshot {snap_path}")

    print(json.dumps(summary, indent=2))
    print(f"Wrote {out_dir / 'report.json'}")
    return 0


def _naitv_version() -> str | None:
    if shutil.which("naitv-mcp") is None:
        return None
    return "naitv-mcp:present"


if __name__ == "__main__":
    sys.exit(main())
