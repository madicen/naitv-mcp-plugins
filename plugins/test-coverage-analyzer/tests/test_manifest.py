"""Manifest checks for test-coverage-analyzer."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "test-coverage-analyzer"
    assert {e["name"] for e in data["entries"]} == set(['run_coverage', 'parse_coverage_report', 'find_uncovered_changes', 'coverage_delta'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
