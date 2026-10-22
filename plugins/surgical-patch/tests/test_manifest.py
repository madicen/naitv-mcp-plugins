"""Manifest checks for surgical-patch."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "surgical-patch"
    assert {e["name"] for e in data["entries"]} == set(['generate_minimal_diff', 'validate_patch_scope', 'apply_patch_dry_run'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
