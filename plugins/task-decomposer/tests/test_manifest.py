"""Manifest checks for task-decomposer."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "task-decomposer"
    assert {e["name"] for e in data["entries"]} == set(['decompose_task', 'estimate_steps', 'order_subtasks', 'validate_plan'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
