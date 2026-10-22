"""Manifest checks for code-generation-helper."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "code-generation-helper"
    assert {e["name"] for e in data["entries"]} == set(['list_templates', 'render_template', 'validate_generated_code', 'suggest_template', 'generation_summary'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
