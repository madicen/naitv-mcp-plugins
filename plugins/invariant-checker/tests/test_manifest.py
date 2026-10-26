"""Manifest checks for invariant-checker."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "invariant-checker"
    assert {e["name"] for e in data["entries"]} == set(['load_invariants', 'check_invariants', 'report_invariant_violations', 'add_invariant'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
