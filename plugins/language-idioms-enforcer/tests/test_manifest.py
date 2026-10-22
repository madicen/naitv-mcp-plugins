"""Manifest checks for language-idioms-enforcer."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "language-idioms-enforcer"
    assert {e["name"] for e in data["entries"]} == set(['check_idioms', 'load_idiom_pack', 'suggest_idiom_fix', 'idiom_summary'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
