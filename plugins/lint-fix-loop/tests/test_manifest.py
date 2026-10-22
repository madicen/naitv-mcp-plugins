"""Manifest checks for lint-fix-loop."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "lint-fix-loop"
    assert {e["name"] for e in data["entries"]} == set(['run_linter', 'apply_safe_fixes', 'summarize_lint_results'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
