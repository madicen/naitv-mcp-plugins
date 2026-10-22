"""Manifest checks for team-metrics-collector."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "team-metrics-collector"
    assert {e["name"] for e in data["entries"]} == set(['collect_commit_metrics', 'collect_review_metrics', 'aggregate_metrics', 'export_metrics'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
