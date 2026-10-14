"""Smoke: plugin manifest loads and passes entry lint."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_entry_lint() -> None:
    r = subprocess.run(
        [sys.executable, str(REPO / "testing/contract/run_entry_lint.py"), "plugin-manager"],
        cwd=str(REPO),
        check=False,
    )
    assert r.returncode == 0
