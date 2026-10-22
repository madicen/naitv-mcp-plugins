"""Manifest checks for type-import-stubber."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "type-import-stubber"
    assert {e["name"] for e in data["entries"]} == set(['list_missing_imports', 'generate_type_stubs', 'validate_stubs'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
