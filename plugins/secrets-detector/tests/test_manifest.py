"""Manifest checks for secrets-detector."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "secrets-detector"
    assert {e["name"] for e in data["entries"]} == set(['scan_secrets', 'scan_secrets_file', 'list_patterns', 'allowlist_check'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
