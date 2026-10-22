"""L1: mistake-tracker tools."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "tools" / "mistake-tracker"
FIXTURES = REPO / "testing" / "fixtures"
sys.path.insert(0, str(TOOLS))
import mistake_tracker as mt  # noqa: E402


class _FakeStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)


@pytest.fixture()
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / ".cache"))
    return tmp_path


def test_record_search_stats(home: Path) -> None:
    root = FIXTURES / "empty"
    rec = mt.record_mistake(
        root, "forgot null check", "null", "pkg/a.py", recorded_at=1700000000
    )
    assert rec["stored"] is True
    mt.record_mistake(
        root, "forgot null check", "null", "pkg/b.py", recorded_at=1700000001
    )
    found = mt.search_mistakes(root, "null")
    assert found["count"] >= 1
    assert any("null" in m["description"] for m in found["matches"])
    recuring = mt.list_recurring_mistakes(root, min_count=2)
    assert recuring["count"] == 1
    st = mt.mistake_stats(root)
    assert st["total"] == 2
    assert st["by_category"][0]["category"] == "null"


def test_search_empty(home: Path) -> None:
    out = mt.search_mistakes(FIXTURES / "empty", "xyz")
    assert out["matches"] == []
    assert out["count"] == 0


def test_validate_root(home: Path) -> None:
    with pytest.raises(SystemExit):
        mt.validate_root_path("/tmp/../etc")


def test_main_search(home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "search_mistakes")
    payload = {"root_path": str(FIXTURES / "empty"), "query": "x"}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    mt.main()
    out = json.loads(capsys.readouterr().out)
    assert out["count"] == 0


def test_main_record(home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "record_mistake")
    payload = {
        "root_path": str(FIXTURES / "empty"),
        "description": "off by one",
        "category": "logic",
        "file": "math.py",
        "recorded_at": 1700000000,
    }
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    mt.main()
    out = json.loads(capsys.readouterr().out)
    assert out["stored"] is True
    assert len(out["id"]) == 12


def test_main_list(home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "list_recurring_mistakes")
    payload = {"root_path": str(FIXTURES / "empty"), "min_count": 2}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    mt.main()
    out = json.loads(capsys.readouterr().out)
    assert out["recurring"] == []


def test_main_stats(home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "mistake_stats")
    payload = {"root_path": str(FIXTURES / "empty")}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    mt.main()
    out = json.loads(capsys.readouterr().out)
    assert out["total"] == 0


def test_main_missing_query(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "search_mistakes")
    monkeypatch.setattr(
        sys, "stdin", _FakeStdin(b'{"root_path":"' + str(FIXTURES / "empty").encode() + b'"}\n')
    )
    with pytest.raises(SystemExit):
        mt.main()


def test_main_bad_json(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "mistake_stats")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{bad\n"))
    with pytest.raises(SystemExit):
        mt.main()


def test_main_unknown(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "nope")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        mt.main()


def test_main_missing_root(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "mistake_stats")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        mt.main()


def test_bad_category(home: Path) -> None:
    with pytest.raises(SystemExit):
        mt.record_mistake(FIXTURES / "empty", "x", "bad cat", "a.py")


def test_stats_since(home: Path) -> None:
    root = FIXTURES / "empty"
    mt.record_mistake(root, "old", "a", "f.py", recorded_at=100.0)
    mt.record_mistake(root, "new", "b", "g.py", recorded_at=200.0)
    st = mt.mistake_stats(root, since=150)
    assert st["total"] == 1
    assert st["by_category"][0]["category"] == "b"
