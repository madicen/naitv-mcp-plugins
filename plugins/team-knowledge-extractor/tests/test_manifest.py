"""Manifest checks for team-knowledge-extractor."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "team-knowledge-extractor"
    assert {e["name"] for e in data["entries"]} == set(['mine_conventions', 'extract_ownership', 'extract_review_patterns', 'export_knowledge_base'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
