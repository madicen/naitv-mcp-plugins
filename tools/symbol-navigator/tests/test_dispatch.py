import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import symbol_navigator

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


def run_cli(
    tool: str,
    home: Path,
    payload: dict | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["TOOL_NAME"] = tool
    return subprocess.run(
        [sys.executable, str(ROOT / "symbol_navigator.py")],
        input=json.dumps(payload or {"root_path": str(FIXTURES), "depth": 2}) + "\n",
        capture_output=True,
        text=True,
        env=env,
    )


def test_find_definition_and_cache_hit(tmp_path):
    payload = {
        "root_path": str(FIXTURES),
        "depth": 2,
        "symbol": "Greeter",
    }
    first = run_cli("find_symbol_definition", tmp_path / "home", payload)
    second = run_cli("find_symbol_definition", tmp_path / "home", payload)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert json.loads(first.stdout)["cached"] is False
    result = json.loads(second.stdout)
    assert result["cached"] is True
    assert result["type"] == "function"
    assert result["file"].endswith("refs_sample.py")
    assert result["source"] == "ast"


def test_search_pattern_dispatch(tmp_path):
    proc = run_cli(
        "search_by_pattern",
        tmp_path / "home",
        {
            "root_path": str(FIXTURES),
            "depth": 2,
            "pattern": "^Greet",
        },
    )

    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert [item["name"] for item in result["results"]] == ["Greeter"]


def test_references_dispatch_is_heuristic(tmp_path):
    proc = run_cli(
        "get_symbol_references",
        tmp_path / "home",
        {
            "root_path": str(FIXTURES),
            "depth": 2,
            "symbol": "Greeter",
            "file_path": str(FIXTURES / "refs_sample.py"),
        },
    )

    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["heuristic"] is True
    assert result["definition"]["type"] == "function"
    assert any("Greeter()" in ref["context"] for ref in result["references"])


def test_unknown_tool_name_exits_nonzero(tmp_path):
    proc = run_cli("unknown_tool", tmp_path / "home")

    assert proc.returncode != 0
    assert "unknown or missing TOOL_NAME" in proc.stderr


def test_invalid_regex_exits_nonzero(tmp_path):
    proc = run_cli(
        "search_by_pattern",
        tmp_path / "home",
        {"root_path": str(FIXTURES), "pattern": "["},
    )

    assert proc.returncode != 0
    assert "invalid regex" in proc.stderr


def test_not_found_returns_empty_collections(tmp_path):
    definition = run_cli(
        "find_symbol_definition",
        tmp_path / "home",
        {"root_path": str(FIXTURES), "symbol": "Missing"},
    )
    references = run_cli(
        "get_symbol_references",
        tmp_path / "home",
        {"root_path": str(FIXTURES), "symbol": "Missing"},
    )

    assert definition.returncode == 0, definition.stderr
    assert references.returncode == 0, references.stderr
    assert json.loads(definition.stdout)["matches"] == []
    refs_result = json.loads(references.stdout)
    assert refs_result["definition"] is None
    assert refs_result["references"] == []
    assert refs_result["heuristic"] is True


def test_ensure_index_does_not_cache_degraded_go(monkeypatch, tmp_path):
    monkeypatch.setattr(symbol_navigator, "load_index", lambda _key: None)
    monkeypatch.setattr(
        symbol_navigator,
        "build_index",
        lambda *_args: ({"defs": [{"name": "PythonOnly"}]}, True),
    )
    saved = []
    monkeypatch.setattr(
        symbol_navigator,
        "save_index",
        lambda key, payload: saved.append((key, payload)),
    )

    definitions, cached, go_degraded = symbol_navigator.ensure_index(
        tmp_path, 3, set(),
    )

    assert definitions == [{"name": "PythonOnly"}]
    assert cached is False
    assert go_degraded is True
    assert saved == []
