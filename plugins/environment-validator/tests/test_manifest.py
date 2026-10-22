"""Manifest checks for environment-validator."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "environment-validator"
    assert {e["name"] for e in data["entries"]} == set(['check_env_vars', 'parse_env_files', 'compare_env_templates', 'env_summary'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
