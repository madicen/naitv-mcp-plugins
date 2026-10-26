"""L1: context-injector tools."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "tools" / "context-injector"
FIXTURES = REPO / "testing" / "fixtures"

sys.path.insert(0, str(TOOLS))
import context_injector as ci  # noqa: E402


class _FakeStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)


def test_get_code_slice() -> None:
    # greeter.py leads with an import; class Greeter starts at line 4
    out = ci.get_code_slice(FIXTURES / "py-small", "pkg/greeter.py", 4, 6)
    assert out["found"] is True
    assert "Greeter" in out["code"]
    assert out["hash"]


def test_get_code_slice_missing() -> None:
    out = ci.get_code_slice(FIXTURES / "empty", "pkg/greeter.py", 1, 2)
    assert out["found"] is False
    assert out["code"] == ""


def test_outline_py() -> None:
    out = ci.get_file_outline(FIXTURES / "py-small", "pkg/greeter.py")
    names = {s["name"] for s in out["symbols"]}
    assert "Greeter" in names
    assert "add" in names


def test_outline_go() -> None:
    out = ci.get_file_outline(FIXTURES / "go-small", "pkg/greeter/greeter.go")
    assert out["found"] is True
    assert out["language"] == "go"
    assert out["symbols"]


def test_snippets() -> None:
    out = ci.find_relevant_snippets(FIXTURES / "py-small", "Greeter", max_tokens=200)
    assert out["snippets"]
    assert out["total_tokens"] > 0


def test_validate_root_rejects_traversal() -> None:
    with pytest.raises(SystemExit):
        ci.validate_root_path("/tmp/../etc")


def test_path_rejects_traversal() -> None:
    with pytest.raises(SystemExit):
        ci.resolve_file(FIXTURES / "py-small", "../etc/passwd")


def test_main_slice(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "get_code_slice")
    payload = {
        "root_path": str(FIXTURES / "py-small"),
        "path": "pkg/greeter.py",
        "start_line": 1,
        "end_line": 2,
    }
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    ci.main()
    out = json.loads(capsys.readouterr().out)
    assert out["found"] is True


def test_main_outline(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "get_file_outline")
    payload = {"root_path": str(FIXTURES / "py-small"), "path": "pkg/greeter.py"}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    ci.main()
    out = json.loads(capsys.readouterr().out)
    assert out["symbols"]


def test_main_snippets(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "find_relevant_snippets")
    payload = {"root_path": str(FIXTURES / "py-small"), "query": "add", "max_tokens": 100}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    ci.main()
    out = json.loads(capsys.readouterr().out)
    assert "snippets" in out


def test_main_missing_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "get_file_outline")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b'{"path":"x.py"}\n'))
    with pytest.raises(SystemExit):
        ci.main()


def test_main_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "get_code_slice")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{bad\n"))
    with pytest.raises(SystemExit):
        ci.main()


def test_main_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "nope")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        ci.main()


def test_invalid_lines() -> None:
    with pytest.raises(SystemExit):
        ci.get_code_slice(FIXTURES / "py-small", "pkg/greeter.py", 5, 1)
