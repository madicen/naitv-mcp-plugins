"""Manifest checks for tdd-runner."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "tdd-runner"
    assert {e["name"] for e in data["entries"]} == set(['run_tests', 'failing_test_summary', 'select_tests_for_change'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
