"""Manifest checks for concurrency-checker."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "concurrency-checker"
    assert {e["name"] for e in data["entries"]} == set(['find_shared_state', 'check_locking', 'find_race_candidates', 'concurrency_summary'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
