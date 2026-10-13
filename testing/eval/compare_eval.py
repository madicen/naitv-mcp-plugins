#!/usr/bin/env python3
"""Compare baseline vs treatment using pre-registered §6e thresholds."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RUNS = Path(__file__).resolve().parent / "runs"
BASELINES = Path(__file__).resolve().parent / "baselines"


def load_summary(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("summary") or data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=RUNS / "BASELINE_NAVIGATION_V1.json",
    )
    parser.add_argument(
        "--treatment",
        type=Path,
        default=RUNS / "TREATMENT_NAVIGATION_V1.json",
    )
    args = parser.parse_args()

    if not args.baseline.is_file():
        # fall back to committed snapshot
        snap = BASELINES / "navigation-v1-baseline.json"
        if snap.is_file():
            args.baseline = snap
        else:
            print(f"missing baseline: {args.baseline}", file=sys.stderr)
            return 2
    if not args.treatment.is_file():
        print(f"missing treatment: {args.treatment}", file=sys.stderr)
        return 2

    b = json.loads(args.baseline.read_text(encoding="utf-8"))
    t = json.loads(args.treatment.read_text(encoding="utf-8"))
    bs, ts = b.get("summary") or b, t.get("summary") or t
    thr = (t.get("thresholds_preregistered") or b.get("thresholds_preregistered") or {})

    b_rate = float(bs.get("success_rate") or 0)
    t_rate = float(ts.get("success_rate") or 0)
    delta_pp = (t_rate - b_rate) * 100

    b_ctrl = bs.get("control_success_rate")
    t_ctrl = ts.get("control_success_rate")
    ctrl_drop_pp = None
    if b_ctrl is not None and t_ctrl is not None:
        ctrl_drop_pp = (float(b_ctrl) - float(t_ctrl)) * 100

    b_hall = bs.get("mean_nonexistent_symbol_rate")
    t_hall = ts.get("mean_nonexistent_symbol_rate")
    hall_rel = None
    if b_hall and t_hall is not None and float(b_hall) > 0:
        hall_rel = (float(b_hall) - float(t_hall)) / float(b_hall)

    helps_pp = float(thr.get("helps_success_pp", 10))
    harm_ctrl = float(thr.get("harmful_control_drop_pp", 2))
    helps_hall = float(thr.get("helps_hallucination_relative_drop", 0.30))

    helps = delta_pp >= helps_pp
    harmful = ctrl_drop_pp is not None and ctrl_drop_pp > harm_ctrl
    hall_helps = hall_rel is not None and hall_rel >= helps_hall

    print("Baseline success_rate:", b_rate)
    print("Treatment success_rate:", t_rate)
    print(f"Delta: {delta_pp:.1f} pp (helps gate ≥ {helps_pp} pp) -> {'PASS' if helps else 'FAIL'}")
    if ctrl_drop_pp is not None:
        print(
            f"Control drop: {ctrl_drop_pp:.1f} pp (harmful if > {harm_ctrl}) -> "
            f"{'HARMFUL' if harmful else 'OK'}"
        )
    if hall_rel is not None:
        print(
            f"Hallucination relative drop: {hall_rel:.2%} "
            f"(helps gate ≥ {helps_hall:.0%}) -> {'PASS' if hall_helps else 'FAIL'}"
        )
    print("Treatment tool_calls:", ts.get("total_tool_calls"))

    # Exit 0 even if gates fail — comparison itself succeeded; gates are reported.
    return 0


if __name__ == "__main__":
    sys.exit(main())
