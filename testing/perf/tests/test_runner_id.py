from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_perf as rp


def test_runner_id_reads_env(monkeypatch):
    monkeypatch.setenv("PERF_RUNNER_ID", "ci-nightly-box-1")
    assert rp.runner_id() == "ci-nightly-box-1"


def test_runner_id_none_when_unset(monkeypatch):
    monkeypatch.delenv("PERF_RUNNER_ID", raising=False)
    assert rp.runner_id() is None
