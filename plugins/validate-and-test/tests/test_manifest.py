"""Manifest checks for validate-and-test."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "validate-and-test"
    assert {e["name"] for e in data["entries"]} == set(['detect_build_system', 'run_validation', 'summarize_failures'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
