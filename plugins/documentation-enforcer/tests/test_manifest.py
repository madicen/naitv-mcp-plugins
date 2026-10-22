"""Manifest checks for documentation-enforcer."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "documentation-enforcer"
    assert {e["name"] for e in data["entries"]} == set(['find_undocumented', 'check_doc_comments', 'generate_doc_stub', 'doc_coverage_report'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
