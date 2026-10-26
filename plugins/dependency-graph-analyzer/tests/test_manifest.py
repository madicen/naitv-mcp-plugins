"""Manifest checks for dependency-graph-analyzer."""
from __future__ import annotations

import json
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]


def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "dependency-graph-analyzer"
    names = {e["name"] for e in data["entries"]}
    assert names == {
        "build_import_graph",
        "query_dependencies",
        "find_hubs",
        "export_graph",
    }


def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
    assert data["layers"]["l5"] is True
    assert "deps-mini" in data["golden"]["fixtures"]
