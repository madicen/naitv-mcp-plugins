"""Manifest checks for documentation-sync-manager."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "documentation-sync-manager"
    assert {e["name"] for e in data["entries"]} == set(['find_doc_drift', 'check_examples', 'list_stale_docs', 'sync_report'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
