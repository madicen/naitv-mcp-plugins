"""L3 perf smoke for structural-anchor (nightly).

Full 50k gate: `python testing/perf/run_perf.py structural-anchor`
This pytest module runs a small fixture count so local/CI opt-in stays cheap.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_PERF = REPO_ROOT / "testing" / "perf" / "run_perf.py"

pytestmark = [
    pytest.mark.perf,
    pytest.mark.skipif(
        os.environ.get("RUN_PERF") != "1",
        reason="set RUN_PERF=1 to run L3 perf (nightly)",
    ),
]


def test_get_project_map_perf_smoke(tmp_path: Path) -> None:
    out = tmp_path / "generated-smoke"
    proc = subprocess.run(
        [
            sys.executable,
            str(RUN_PERF),
            "structural-anchor",
            "--files",
            "200",
            "--seed",
            "42",
            "--runs",
            "3",
            "--warmups",
            "1",
            "--out",
            str(out),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
