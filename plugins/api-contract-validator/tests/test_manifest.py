"""Manifest checks for api-contract-validator."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "api-contract-validator"
    assert {e["name"] for e in data["entries"]} == set(['extract_api', 'diff_api', 'check_breaking_changes', 'list_contracts'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
