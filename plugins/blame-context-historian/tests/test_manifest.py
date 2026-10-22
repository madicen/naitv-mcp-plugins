"""Manifest checks for blame-context-historian."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "blame-context-historian"
    assert {e["name"] for e in data["entries"]} == set(['blame_lines', 'history_for_symbol', 'recent_changes_summary', 'find_last_change_author'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
