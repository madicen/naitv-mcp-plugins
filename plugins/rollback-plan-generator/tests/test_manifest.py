"""Manifest checks for rollback-plan-generator."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "rollback-plan-generator"
    assert {e["name"] for e in data["entries"]} == set(['analyze_change_risk', 'generate_rollback_steps', 'list_affected_services', 'validate_rollback_plan'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
