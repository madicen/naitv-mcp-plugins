#!/usr/bin/env python3
"""L3 performance runner driven by plugins/<name>/harness.json → perf."""
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
sys.path.insert(0, str(REPO_ROOT / "testing"))

from plugin_harness import load_harness, resolve_impl_paths  # noqa: E402

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
    expected = f"files={files} seed={seed} v=2\n"  # v=2: PerfAnchor planted
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


def load_module(plugin_name: str, module_name: str) -> Any:
    paths = resolve_impl_paths(plugin_name, load_harness(plugin_name))
    for p in paths:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


def clear_subdir(home: Path, subdir: str) -> None:
    d = home / ".cache" / "naitv-mcp" / subdir
    if d.is_dir():
        shutil.rmtree(d)


def clear_go_bin(home: Path) -> None:
    d = home / ".cache" / "naitv-mcp" / "bin"
    if d.is_dir():
        shutil.rmtree(d)


def call_hot(
    mod: Any,
    call_name: str,
    root: Path,
    call_args: list[Any] | None = None,
    call_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fn = getattr(mod, call_name)
    skip = set(getattr(mod, "DEFAULT_SKIP_DIRS", set()))
    # lazy: (root, depth, skip_dirs, *call_args) matches structural-anchor + symbol-navigator
    return fn(root, 3, skip, *(call_args or []), **(call_kwargs or {}))


def timed(fn: Callable[[], Any]) -> float:
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


def measure_series(
    mod: Any,
    call_name: str,
    root: Path,
    home: Path,
    cache_subdir: str,
    *,
    mode: str,
    runs: int,
    warmups: int,
    call_args: list[Any] | None = None,
    call_kwargs: dict[str, Any] | None = None,
) -> list[float]:
    os.environ["HOME"] = str(home)

    def once() -> None:
        call_hot(mod, call_name, root, call_args, call_kwargs)

    if mode == "warm":
        clear_subdir(home, cache_subdir)
        once()
        for _ in range(warmups):
            once()
        return [timed(once) for _ in range(runs)]

    samples: list[float] = []
    for i in range(warmups + runs):
        clear_subdir(home, cache_subdir)
        elapsed = timed(once)
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
    parser.add_argument("plugin")
    parser.add_argument("--tool", default="")
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

    harness = load_harness(args.plugin)
    perf = harness.get("perf") or {}
    if not perf.get("enabled", False):
        print(f"SKIP: harness.perf.enabled is false for {args.plugin}")
        return 0

    tool = args.tool or perf.get("tool") or ""
    module_name = perf.get("module") or ""
    call_name = perf.get("call") or tool
    cache_subdir = perf.get("cache_subdir") or args.plugin
    call_args = list(perf.get("call_args") or [])
    call_kwargs = dict(perf.get("call_kwargs") or {})
    targets = perf.get("targets_seconds") or {}
    if not tool or not module_name or not call_name:
        raise SystemExit("harness.perf requires tool, module, and call")

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
        "tool": tool,
        "files": args.files,
        "seed": args.seed,
        "runs": args.runs,
        "warmups": args.warmups,
        "call_args": call_args,
        "call_kwargs": call_kwargs,
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
        mod = load_module(args.plugin, module_name)

        if "cold_start" in targets:
            print("\n=== cold_start (helper compile + first call) ===")
            clear_subdir(home, cache_subdir)
            clear_go_bin(home)
            try:
                cold_start = timed(
                    lambda: call_hot(mod, call_name, root, call_args, call_kwargs)
                )
            except Exception as exc:
                print(f"  FAIL cold_start: {exc}")
                failures += 1
                cold_start = float("nan")
            else:
                report["modes"]["cold_start"] = {"seconds": cold_start}
                if not check_target("cold_start", cold_start, float(targets["cold_start"])):
                    failures += 1

        if "cold" in targets:
            print("\n=== cold (empty cache, helpers kept) ===")
            cold_samples = measure_series(
                mod,
                call_name,
                root,
                home,
                cache_subdir,
                mode="cold",
                runs=args.runs,
                warmups=args.warmups,
                call_args=call_args,
                call_kwargs=call_kwargs,
            )
            cold_stats = summarize(cold_samples)
            report["modes"]["cold"] = {"samples": cold_samples, **cold_stats}
            print(
                f"  samples p50={cold_stats['p50']:.4f}s p95={cold_stats['p95']:.4f}s "
                f"mean={cold_stats['mean']:.4f}s"
            )
            if not check_target("cold", cold_stats["p95"], float(targets["cold"])):
                failures += 1

        if "warm" in targets:
            print("\n=== warm (populated cache) ===")
            warm_samples = measure_series(
                mod,
                call_name,
                root,
                home,
                cache_subdir,
                mode="warm",
                runs=args.runs,
                warmups=args.warmups,
                call_args=call_args,
                call_kwargs=call_kwargs,
            )
            warm_stats = summarize(warm_samples)
            report["modes"]["warm"] = {"samples": warm_samples, **warm_stats}
            print(
                f"  samples p50={warm_stats['p50']:.4f}s p95={warm_stats['p95']:.4f}s "
                f"mean={warm_stats['mean']:.4f}s"
            )
            if not check_target("warm", warm_stats["p95"], float(targets["warm"])):
                failures += 1

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["failures"] = failures
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"{args.plugin}-{tool}-{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    latest = RESULTS_DIR / f"{args.plugin}-{tool}-latest.json"
    latest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out_path}")
    print(f"Summary: failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
