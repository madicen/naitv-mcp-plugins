"""Manifest checks for database-schema-validator."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "database-schema-validator"
    assert {e["name"] for e in data["entries"]} == set(['parse_schema', 'validate_schema', 'check_migrations', 'check_orm_usage', 'schema_summary'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
