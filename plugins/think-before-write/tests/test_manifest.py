"""Manifest checks for think-before-write."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "think-before-write"
    assert {e["name"] for e in data["entries"]} == set(['plan_checklist', 'check_assumptions', 'render_pre_write_prompt'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
