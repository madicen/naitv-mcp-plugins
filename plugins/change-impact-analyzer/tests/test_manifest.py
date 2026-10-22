"""Manifest checks for change-impact-analyzer."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "change-impact-analyzer"
    assert {e["name"] for e in data["entries"]} == set(['analyze_change_impact', 'list_affected_tests', 'affected_modules', 'impact_summary'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
