"""Manifest checks for naming-validator."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "naming-validator"
    assert {e["name"] for e in data["entries"]} == set(['check_names', 'suggest_names', 'list_violations', 'load_naming_rules'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
