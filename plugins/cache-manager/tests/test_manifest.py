"""Manifest checks for cache-manager."""
from __future__ import annotations

import json
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]


def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "cache-manager"
    names = {e["name"] for e in data["entries"]}
    assert names == {"cache_get", "cache_put", "cache_stats", "cache_prune"}


def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
    assert data["layers"]["l5"] is False
