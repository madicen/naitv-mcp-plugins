"""Manifest checks for fuzzing-test-generator."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "fuzzing-test-generator"
    assert {e["name"] for e in data["entries"]} == set(['find_fuzz_targets', 'generate_fuzz_target', 'validate_fuzz_target', 'run_fuzz_smoke'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
