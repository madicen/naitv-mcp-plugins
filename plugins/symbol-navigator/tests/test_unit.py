"""L1: call symbol-navigator tools in-process (coverage + contract shapes)."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "tools" / "symbol-navigator"
FIXTURES = REPO / "testing" / "fixtures"

sys.path.insert(0, str(TOOLS))
import symbol_navigator as sn  # noqa: E402


@pytest.fixture()
def skip_dirs() -> set[str]:
    return set(sn.DEFAULT_SKIP_DIRS)


class _FakeStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)


def test_find_definition_py_small(skip_dirs: set[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = FIXTURES / "py-small"
    out = sn.find_symbol_definition(root, 3, skip_dirs, "Greeter")
    assert out["type"] == "class"
    assert out["file"].endswith("greeter.py")
    assert out["source"] == "ast"


def test_search_by_pattern_py_small(skip_dirs: set[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = FIXTURES / "py-small"
    out = sn.search_by_pattern(root, 3, skip_dirs, "^Greet")
    names = [r["name"] for r in out["results"]]
    assert "Greeter" in names


def test_get_symbol_references_shape(skip_dirs: set[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = FIXTURES / "py-small"
    out = sn.get_symbol_references(root, 3, skip_dirs, "Greeter")
    assert out["heuristic"] is True
    assert "references" in out
    assert out["definition"] is None or out["definition"]["type"] == "class"


def test_find_missing_symbol(skip_dirs: set[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    out = sn.find_symbol_definition(FIXTURES / "empty", 1, skip_dirs, "Nope")
    assert out["matches"] == []


def test_validate_root_rejects_traversal() -> None:
    with pytest.raises(SystemExit):
        sn.validate_root_path("/tmp/../etc")


def test_validate_root_rejects_missing(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        sn.validate_root_path(str(tmp_path / "missing"))


def test_main_find_definition(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("TOOL_NAME", "find_symbol_definition")
    payload = {
        "root_path": str(FIXTURES / "py-small"),
        "depth": 3,
        "symbol": "Greeter",
    }
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    sn.main()
    out = json.loads(capsys.readouterr().out)
    assert out["type"] == "class"


def test_main_search_and_missing_symbol(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("TOOL_NAME", "search_by_pattern")
    payload = {"root_path": str(FIXTURES / "py-small"), "depth": 3, "pattern": "^add$"}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    sn.main()
    out = json.loads(capsys.readouterr().out)
    assert "results" in out

    monkeypatch.setenv("TOOL_NAME", "find_symbol_definition")
    monkeypatch.setattr(
        sys,
        "stdin",
        _FakeStdin((json.dumps({"root_path": str(FIXTURES / "py-small"), "symbol": ""}) + "\n").encode()),
    )
    with pytest.raises(SystemExit):
        sn.main()


def test_main_rejects_oversize(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("TOOL_NAME", "find_symbol_definition")
    huge = b'{"root_path":"/tmp","pad":"' + b"x" * (sn.MAX_INPUT_BYTES + 1) + b'"}'
    monkeypatch.setattr(sys, "stdin", _FakeStdin(huge))
    with pytest.raises(SystemExit):
        sn.main()


def test_go_small_find_and_refs(skip_dirs: set[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = FIXTURES / "go-small"
    found = sn.find_symbol_definition(root, 3, skip_dirs, "Greeter")
    assert found.get("type") == "type" or found.get("matches") == []
    refs = sn.get_symbol_references(root, 3, skip_dirs, "Add")
    assert refs["heuristic"] is True
