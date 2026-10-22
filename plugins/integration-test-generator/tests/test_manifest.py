"""Manifest checks for integration-test-generator."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "integration-test-generator"
    assert {e["name"] for e in data["entries"]} == set(['find_integration_points', 'generate_integration_test', 'validate_test_file', 'list_fixtures'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
