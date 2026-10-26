"""Manifest checks for code-style-enforcer."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "code-style-enforcer"
    assert {e["name"] for e in data["entries"]} == set(['check_style', 'load_style_rules', 'suggest_fixes', 'style_summary'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
