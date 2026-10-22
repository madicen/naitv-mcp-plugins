"""Manifest checks for incremental-refactoring-helper."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "incremental-refactoring-helper"
    assert {e["name"] for e in data["entries"]} == set(['plan_refactor_steps', 'next_step', 'track_refactor_state', 'mark_step_done'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
