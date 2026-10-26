"""Manifest checks for regression-test-generator."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "regression-test-generator"
    assert {e["name"] for e in data["entries"]} == set(['suggest_regression_tests', 'generate_test_stub', 'validate_generated_test'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
