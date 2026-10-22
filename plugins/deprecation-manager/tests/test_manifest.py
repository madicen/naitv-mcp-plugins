"""Manifest checks for deprecation-manager."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "deprecation-manager"
    assert {e["name"] for e in data["entries"]} == set(['find_deprecated', 'list_deprecations', 'check_deprecated_usage', 'plan_migration'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
