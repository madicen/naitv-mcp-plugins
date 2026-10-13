from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_eval import task_dir


def test_task_dir_default():
    p = task_dir("navigation", 1, held_out=False)
    assert p.as_posix().endswith("tasks/navigation/v1")


def test_task_dir_held_out():
    p = task_dir("navigation", 1, held_out=True)
    assert p.as_posix().endswith("tasks/navigation/held-out/v1")
