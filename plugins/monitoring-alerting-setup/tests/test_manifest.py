"""Manifest checks for monitoring-alerting-setup."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "monitoring-alerting-setup"
    assert {e["name"] for e in data["entries"]} == set(['detect_metrics', 'generate_alert_rules', 'validate_alert_rules', 'render_dashboard_config'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
