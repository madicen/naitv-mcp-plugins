"""Manifest checks for code-review-simulator."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "code-review-simulator"
    assert {e["name"] for e in data["entries"]} == set(['review_diff', 'score_risk', 'list_reviewer_questions', 'suggest_tests'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
