"""Manifest checks for doc-scraper."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "doc-scraper"
    assert {e["name"] for e in data["entries"]} == set(['fetch_and_parse', 'extract_sections', 'search_doc_index'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
