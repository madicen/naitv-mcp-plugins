"""Manifest checks for mistake-tracker."""
from __future__ import annotations

import json
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]


def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "mistake-tracker"
    names = [e["name"] for e in data["entries"]]
    assert names[0] == "search_mistakes"
    assert set(names) == {
        "record_mistake",
        "search_mistakes",
        "list_recurring_mistakes",
        "mistake_stats",
    }


def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["layers"]["l5"] is True
    assert data["l5"]["gate"]["min_success_delta_pp"] == 10
