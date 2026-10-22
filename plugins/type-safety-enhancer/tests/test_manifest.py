"""Manifest checks for type-safety-enhancer."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "type-safety-enhancer"
    assert {e["name"] for e in data["entries"]} == set(['infer_types', 'find_untyped_symbols', 'suggest_annotations', 'type_coverage_report'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
