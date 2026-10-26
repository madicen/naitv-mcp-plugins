"""Manifest checks for golden-example-injector."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "golden-example-injector"
    assert {e["name"] for e in data["entries"]} == set(['find_golden_examples', 'rank_golden_examples', 'inject_example'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
