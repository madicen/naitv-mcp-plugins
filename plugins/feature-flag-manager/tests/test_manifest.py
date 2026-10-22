"""Manifest checks for feature-flag-manager."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "feature-flag-manager"
    assert {e["name"] for e in data["entries"]} == set(['find_flags', 'list_stale_flags', 'plan_flag_removal', 'flag_summary'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
