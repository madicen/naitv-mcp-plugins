"""Manifest checks for license-compliance-checker."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "license-compliance-checker"
    assert {e["name"] for e in data["entries"]} == set(['list_dependency_licenses', 'check_license_policy', 'find_license_conflicts', 'license_summary'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
