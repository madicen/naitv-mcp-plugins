"""Manifest checks for circular-dependency-detector."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "circular-dependency-detector"
    assert {e["name"] for e in data["entries"]} == set(['find_cycles', 'cycle_path', 'suggest_break_points', 'check_change_cycles'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
