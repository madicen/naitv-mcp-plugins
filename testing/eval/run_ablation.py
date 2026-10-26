#!/usr/bin/env python3
"""Leave-one-out ablation over suite treatment_plugins.

Agents:
  stub   — deterministic; default for CI safety
  ollama — local model; function-calling tool loop (same as run_eval.py)
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

EVAL_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_ROOT))

from mcp_session import mcp_session  # noqa: E402
from run_eval import (  # noqa: E402
    load_tasks,
    run_task,
    summarize,
    treatment_plugins_for,
)

RUNS_ROOT = EVAL_ROOT / "runs"


def leave_one_out_sets(plugins: list[str]) -> list[tuple[str, list[str]]]:
    """Return (dropped, remaining) for each plugin in the full treatment set."""
    return [(p, [x for x in plugins if x != p]) for p in plugins]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="navigation")
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--seed-base", type=int, default=42)
    parser.add_argument("--agent", choices=("stub", "ollama"), default="stub")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if shutil.which("naitv-mcp") is None:
        print("warn: naitv-mcp not on PATH; ablation skipped", file=sys.stderr)
        return 0

    full = treatment_plugins_for(args.suite)
    if len(full) < 2:
        print(f"warn: need ≥2 treatment plugins for ablation; got {full}", file=sys.stderr)
        return 0

    tasks = load_tasks(args.suite, args.version, held_out=False)
    arms: list[dict[str, Any]] = []

    for dropped, remaining in leave_one_out_sets(full):
        results: list[dict[str, Any]] = []
        with mcp_session(plugins=remaining) as client:
            order = list(tasks)
            random.Random(args.seed_base).shuffle(order)
            for task in order:
                for i in range(args.seeds):
                    results.append(
                        run_task(
                            task,
                            condition="treatment",
                            agent=args.agent,
                            seed=args.seed_base + i,
                            client=client,
                            plugins=remaining,
                        )
                    )
        arms.append(
            {
                "dropped": dropped,
                "plugins": remaining,
                "summary": summarize(results),
                "n_results": len(results),
            }
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = RUNS_ROOT / f"ablation-{args.suite}-v{args.version}-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "kind": "ablation",
        "suite": args.suite,
        "suite_version": args.version,
        "full_plugins": full,
        "agent": args.agent,
        "model": os.environ.get("OLLAMA_MODEL", "qwen3:8b")
        if args.agent == "ollama"
        else None,
        "seeds": args.seeds,
        "arms": arms,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "runner_id": os.environ.get("PERF_RUNNER_ID"),
    }
    path = out_dir / "report.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    latest = RUNS_ROOT / f"ablation-{args.suite}-v{args.version}-latest.json"
    latest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"arms": [{"dropped": a["dropped"], "summary": a["summary"]} for a in arms]}, indent=2))
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
