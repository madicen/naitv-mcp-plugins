"""Manifest checks for interface-segregation-enforcer."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "interface-segregation-enforcer"
    assert {e["name"] for e in data["entries"]} == set(['list_interfaces', 'find_fat_interfaces', 'suggest_split', 'check_implementations'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
