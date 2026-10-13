from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_ablation import leave_one_out_sets


def test_leave_one_out_sets():
    full = ["structural-anchor", "symbol-navigator"]
    sets = leave_one_out_sets(full)
    assert sets == [
        ("structural-anchor", ["symbol-navigator"]),
        ("symbol-navigator", ["structural-anchor"]),
    ]
