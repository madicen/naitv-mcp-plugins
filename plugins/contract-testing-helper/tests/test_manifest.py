"""Manifest checks for contract-testing-helper."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "contract-testing-helper"
    assert {e["name"] for e in data["entries"]} == set(['generate_contract', 'verify_contract', 'list_consumers', 'contract_summary'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
