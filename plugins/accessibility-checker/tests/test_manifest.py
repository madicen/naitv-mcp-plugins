"""Manifest checks for accessibility-checker."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "accessibility-checker"
    assert {e["name"] for e in data["entries"]} == set(['check_a11y_file', 'list_a11y_rules', 'a11y_summary', 'suggest_a11y_fixes'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
