"""Manifest checks for benchmark-generator."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "benchmark-generator"
    assert {e["name"] for e in data["entries"]} == set(['find_bench_targets', 'generate_benchmark', 'validate_benchmark', 'run_benchmark_once', 'list_benchmarks'])

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
