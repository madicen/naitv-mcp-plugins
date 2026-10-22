from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_ablation import build_parser, leave_one_out_sets


def test_leave_one_out_sets():
    full = ["structural-anchor", "symbol-navigator"]
    sets = leave_one_out_sets(full)
    assert sets == [
        ("structural-anchor", ["symbol-navigator"]),
        ("symbol-navigator", ["structural-anchor"]),
    ]


def test_agent_choices_include_ollama_default_stub():
    parser = build_parser()
    stub = parser.parse_args([])
    assert stub.agent == "stub"
    ollama = parser.parse_args(["--agent", "ollama"])
    assert ollama.agent == "ollama"
