"""Manifest checks for decision-log-runner."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "decision-log-runner"
    assert {e["name"] for e in data["entries"]} == set(['parse_decision_log', 'search_decisions', 'check_decision_conflicts', 'summarize_decisions'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
