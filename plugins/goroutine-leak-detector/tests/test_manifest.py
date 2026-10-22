"""Manifest checks for goroutine-leak-detector."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "goroutine-leak-detector"
    assert {e["name"] for e in data["entries"]} == set(['parse_goroutine_dump', 'find_leak_candidates', 'explain_goroutine', 'leak_summary'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
