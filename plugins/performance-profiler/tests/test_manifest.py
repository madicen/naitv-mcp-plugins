"""Manifest checks for performance-profiler."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "performance-profiler"
    assert {e["name"] for e in data["entries"]} == set(['run_benchmark', 'profile_hotspots', 'compare_profiles', 'summarize_profile'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
