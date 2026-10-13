#!/usr/bin/env python3
"""L3 performance runner: cold/warm p50/p95 for structural-anchor get_project_map.

Measures in-process tool time (matches design targets). Nightly / release gate —
not part of the default ./scripts/test.sh path.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "testing" / "fixtures"
GENERATE = FIXTURES_DIR / "generate.py"
RESULTS_DIR = REPO_ROOT / "testing" / "perf" / "results"

# Targets from TEST_PLAN / design (seconds). Fail if p95 > target * (1 + slack).
TARGETS = {
    "get_project_map": {
        "cold": 2.0,  # map build on ~50k (Go bin already present)
        "warm": 0.1,  # cache hit
        "cold_start": 30.0,  # first call including Go helper compile
    }
}
SLACK = 0.10


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def ensure_fixture(files: int, seed: int, out: Path) -> Path:
    marker = out / ".generated"
    expected = f"files={files} seed={seed}\n"
    if marker.is_file() and marker.read_text(encoding="utf-8") == expected:
        return out
    if out.exists():
        shutil.rmtree(out)
    subprocess.run(
        [
            sys.executable,
            str(GENERATE),
            "--files",
            str(files),
            "--seed",
            str(seed),
            "--out",
            str(out),
        ],
        check=True,
        cwd=str(REPO_ROOT),
    )
    marker.write_text(expected, encoding="utf-8")
    return out


def load_tool(plugin_name: str) -> Any:
    tools = REPO_ROOT / "tools" / plugin_name
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    # Fresh import each process; module may already be loaded in pytest.
    if "structural_anchor" in sys.modules:
        return importlib.reload(sys.modules["structural_anchor"])
    return importlib.import_module("structural_anchor")


def clear_map_cache(home: Path) -> None:
    d = home / ".cache" / "naitv-mcp" / "structural-anchor"
    if d.is_dir():
        shutil.rmtree(d)


def clear_go_bin(home: Path) -> None:
    d = home / ".cache" / "naitv-mcp" / "bin"
    if d.is_dir():
        shutil.rmtree(d)


def call_map(mod: Any, root: Path) -> dict[str, Any]:
    return mod.get_project_map(root, 3, set(mod.DEFAULT_SKIP_DIRS))


def timed(fn: Callable[[], Any]) -> float:
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


def measure_series(
    mod: Any,
    root: Path,
    home: Path,
    *,
    mode: str,
    runs: int,
    warmups: int,
) -> list[float]:
    os.environ["HOME"] = str(home)

    if mode == "warm":
        clear_map_cache(home)
        call_map(mod, root)
        for _ in range(warmups):
            call_map(mod, root)
        return [timed(lambda: call_map(mod, root)) for _ in range(runs)]

    samples: list[float] = []
    for i in range(warmups + runs):
        clear_map_cache(home)
        elapsed = timed(lambda: call_map(mod, root))
        if i >= warmups:
            samples.append(elapsed)
    return samples


def summarize(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "n": float(len(samples)),
        "p50": percentile(ordered, 50),
        "p95": percentile(ordered, 95),
        "mean": statistics.fmean(samples) if samples else float("nan"),
        "min": min(samples) if samples else float("nan"),
        "max": max(samples) if samples else float("nan"),
    }


def check_target(label: str, p95: float, target: float) -> bool:
    limit = target * (1.0 + SLACK)
    ok = p95 <= limit
    status = "PASS" if ok else "FAIL"
    print(f"  {status} {label}: p95={p95:.4f}s target={target:.4f}s limit={limit:.4f}s")
    return ok


def hardware_info() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plugin", nargs="?", default="structural-anchor")
    parser.add_argument("--tool", default="get_project_map")
    parser.add_argument("--files", type=int, default=50_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument(
        "--out",
        type=Path,
        default=FIXTURES_DIR / "generated-50k",
        help="fixture output directory (gitignored)",
    )
    parser.add_argument(
        "--skip-generate",
        action="store_true",
        help="reuse existing --out without regenerating",
    )
    args = parser.parse_args()

    if args.tool != "get_project_map":
        raise SystemExit("only get_project_map is supported in this runner")
    if args.plugin != "structural-anchor":
        raise SystemExit("only structural-anchor is supported in this runner")

    targets = TARGETS[args.tool]

    if args.skip_generate:
        root = args.out
        if not root.is_dir():
            raise SystemExit(f"missing fixture dir {root}")
    else:
        print(f"Generating fixture: files={args.files} seed={args.seed} -> {args.out}")
        root = ensure_fixture(args.files, args.seed, args.out)

    failures = 0
    report: dict[str, Any] = {
        "plugin": args.plugin,
        "tool": args.tool,
        "files": args.files,
        "seed": args.seed,
        "runs": args.runs,
        "warmups": args.warmups,
        "targets": targets,
        "slack": SLACK,
        "measure": "in-process",
        "hardware": hardware_info(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "modes": {},
    }

    with tempfile.TemporaryDirectory(prefix="naitv-perf-") as tmp:
        home = Path(tmp)
        os.environ["HOME"] = str(home)
        mod = load_tool(args.plugin)

        print("\n=== cold_start (Go helper compile + first map) ===")
        clear_map_cache(home)
        clear_go_bin(home)
        try:
            cold_start = timed(lambda: call_map(mod, root))
        except Exception as exc:
            print(f"  FAIL cold_start: {exc}")
            failures += 1
            cold_start = float("nan")
        else:
            report["modes"]["cold_start"] = {"seconds": cold_start}
            if not check_target("cold_start", cold_start, targets["cold_start"]):
                failures += 1

        print("\n=== cold (empty map cache, Go bin kept) ===")
        cold_samples = measure_series(
            mod, root, home, mode="cold", runs=args.runs, warmups=args.warmups
        )
        cold_stats = summarize(cold_samples)
        report["modes"]["cold"] = {"samples": cold_samples, **cold_stats}
        print(
            f"  samples p50={cold_stats['p50']:.4f}s p95={cold_stats['p95']:.4f}s "
            f"mean={cold_stats['mean']:.4f}s"
        )
        if not check_target("cold", cold_stats["p95"], targets["cold"]):
            failures += 1

        print("\n=== warm (populated cache) ===")
        warm_samples = measure_series(
            mod, root, home, mode="warm", runs=args.runs, warmups=args.warmups
        )
        warm_stats = summarize(warm_samples)
        report["modes"]["warm"] = {"samples": warm_samples, **warm_stats}
        print(
            f"  samples p50={warm_stats['p50']:.4f}s p95={warm_stats['p95']:.4f}s "
            f"mean={warm_stats['mean']:.4f}s"
        )
        if not check_target("warm", warm_stats["p95"], targets["warm"]):
            failures += 1

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["failures"] = failures
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"{args.plugin}-{args.tool}-{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    latest = RESULTS_DIR / f"{args.plugin}-{args.tool}-latest.json"
    latest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out_path}")
    print(f"Summary: failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
