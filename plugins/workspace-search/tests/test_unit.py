"""L1: workspace-search tools."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "tools" / "workspace-search"
FIXTURES = REPO / "testing" / "fixtures"

sys.path.insert(0, str(TOOLS))
import workspace_search as ws  # noqa: E402


class _FakeStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)


def test_text_search_greeter() -> None:
    out = ws.text_search(FIXTURES / "py-small", "Greeter", depth=3)
    assert out["count"] >= 1
    paths = {m["path"] for m in out["matches"]}
    assert any("greeter.py" in p for p in paths)


def test_semantic_search_greeter() -> None:
    out = ws.semantic_search(FIXTURES / "py-small", "Greeter", limit=5, depth=3)
    assert out["count"] >= 1
    assert out["results"][0]["score"] > 0


def test_rank_results_orders() -> None:
    out = ws.rank_results(
        "Greeter",
        ["pkg/util/math.py", "pkg/greeter.py", "README.md"],
    )
    assert out["ranked"][0]["path"] == "pkg/greeter.py"


def test_text_search_empty() -> None:
    out = ws.text_search(FIXTURES / "empty", "Greeter", depth=1)
    assert out["matches"] == []


def test_validate_root_rejects_traversal() -> None:
    with pytest.raises(SystemExit):
        ws.validate_root_path("/tmp/../etc")


def test_validate_root_rejects_missing(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        ws.validate_root_path(str(tmp_path / "missing"))


def test_invalid_regex() -> None:
    with pytest.raises(SystemExit):
        ws.text_search(FIXTURES / "py-small", "[")


def test_main_semantic(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "semantic_search")
    payload = {"root_path": str(FIXTURES / "py-small"), "query": "add", "limit": 3}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    ws.main()
    out = json.loads(capsys.readouterr().out)
    assert "results" in out


def test_main_text(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "text_search")
    payload = {"root_path": str(FIXTURES / "py-small"), "pattern": "def add"}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    ws.main()
    out = json.loads(capsys.readouterr().out)
    assert out["count"] >= 1


def test_main_rank(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "rank_results")
    payload = {"query": "math", "candidates": ["a.py", "pkg/util/math.py"]}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    ws.main()
    out = json.loads(capsys.readouterr().out)
    assert out["ranked"][0]["path"] == "pkg/util/math.py"


def test_main_missing_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "semantic_search")
    payload = {"root_path": str(FIXTURES / "py-small")}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    with pytest.raises(SystemExit):
        ws.main()


def test_main_missing_pattern(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "text_search")
    payload = {"root_path": str(FIXTURES / "py-small")}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    with pytest.raises(SystemExit):
        ws.main()


def test_main_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "rank_results")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{bad\n"))
    with pytest.raises(SystemExit):
        ws.main()


def test_main_unknown_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "nope")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        ws.main()


def test_glob_filter() -> None:
    out = ws.text_search(
        FIXTURES / "py-small", "Greeter", depth=3, glob="*.md"
    )
    assert all(m["path"].endswith(".md") or "/" not in m["path"] for m in out["matches"]) or out["count"] == 0


def test_rank_dict_candidates() -> None:
    out = ws.rank_results(
        "Greeter class",
        [{"path": "pkg/greeter.py", "note": "class"}, {"path": "other.py"}],
    )
    assert out["count"] == 2
    assert out["ranked"][0]["path"] == "pkg/greeter.py"
