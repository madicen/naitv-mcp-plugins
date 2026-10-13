"""Catalog layout: only plugins/<name>/plugin.json (no flat plugins/*.json)."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLUGINS = REPO / "plugins"


def test_no_flat_plugin_json():
    flats = sorted(PLUGINS.glob("*.json"))
    assert flats == [], f"legacy flat manifests still present: {flats}"


def test_every_plugin_dir_has_plugin_json():
    dirs = [p for p in PLUGINS.iterdir() if p.is_dir() and not p.name.startswith(".")]
    assert dirs, "no plugin directories"
    missing = [p.name for p in dirs if not (p / "plugin.json").is_file()]
    assert missing == [], f"missing plugin.json: {missing}"
