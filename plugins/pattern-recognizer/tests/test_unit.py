"""L1 unit tests for pattern-recognizer."""
from __future__ import annotations
import io, json, sys
from pathlib import Path
import pytest
REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "tools" / "pattern-recognizer"
FIXTURES = REPO / "testing" / "fixtures"
sys.path.insert(0, str(TOOLS))
import pattern_recognizer as mod  # noqa: E402

class _FakeStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)

def test_handle_empty() -> None:
    out = mod.handle('find_pattern_instances', FIXTURES / "empty", {"query": "x", "depth": 2})
    assert isinstance(out, dict)
    assert out["count"] == 0
    assert out["items"] == []

def test_handle_py_small() -> None:
    out = mod.handle('find_pattern_instances', FIXTURES / "py-small", {"query": "Greeter", "depth": 3})
    assert isinstance(out, dict)
    assert out["count"] >= 1
    paths = {i["path"] for i in out["items"]}
    assert any("greeter.py" in p for p in paths)
    for item in out["items"]:
        assert "path" in item
        assert "name" in item
        assert item["name"]  # real token from file

def test_detect_repeated_on_tmp(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("import os\n\ndef foo():\n    return os.getcwd()\n    # pad\n")
    (tmp_path / "b.py").write_text("import os\n\ndef bar():\n    return 1\n")
    out = mod.handle("detect_repeated_patterns", tmp_path, {"depth": 2, "limit": 10})
    assert out["ok"] is True
    assert out["tool"] == "detect_repeated_patterns"
    # repeated import os
    names = [p["name"] for p in out["items"]]
    assert any("import os" in n for n in names)

def test_handle_all_branches() -> None:
    root = FIXTURES / "py-small"
    data = {"query": "Greeter", "path": "README.md", "depth": 3, "limit": 5}
    for fake in (
        "list_things",
        "check_things",
        "generate_things",
        "run_things",
        "load_things",
        "add_things",
        "custom_op",
    ):
        out = mod.handle(fake, root, data)
        assert isinstance(out, dict)

def test_validate_traversal() -> None:
    with pytest.raises(SystemExit):
        mod.validate_root_path("/tmp/../etc")

def test_main_ok(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", 'find_pattern_instances')
    payload = {"root_path": str(FIXTURES / "empty"), "query": "x"}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    mod.main()
    out = json.loads(capsys.readouterr().out)
    assert isinstance(out, dict)

def test_main_missing_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", 'find_pattern_instances')
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        mod.main()

def test_main_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", 'find_pattern_instances')
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{bad\n"))
    with pytest.raises(SystemExit):
        mod.main()

def test_main_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "nope")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        mod.main()

def test_main_all_tools(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    for tool in ['find_pattern_instances', 'detect_repeated_patterns', 'rank_examples', 'pattern_summary']:
        monkeypatch.setenv("TOOL_NAME", tool)
        payload = {"root_path": str(FIXTURES / "py-small"), "query": "Greeter", "path": "README.md", "limit": 5}
        monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
        mod.main()
        out = json.loads(capsys.readouterr().out)
        assert isinstance(out, dict)
        if tool in ("detect_repeated_patterns", "rank_examples"):
            assert out.get("ok") is True
            assert out.get("tool") == tool
        else:
            assert "items" in out and "count" in out

def test_iter_files() -> None:
    files = mod.iter_files(FIXTURES / "py-small", depth=3)
    assert any(p.name.endswith(".py") for p in files)

def test_main_too_large(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", 'find_pattern_instances')
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{" + b"a" * (mod.MAX_INPUT_BYTES + 5)))
    with pytest.raises(SystemExit):
        mod.main()

def test_main_non_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", 'find_pattern_instances')
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"[]\n"))
    with pytest.raises(SystemExit):
        mod.main()

def test_rank_and_summary(tmp_path: Path) -> None:
    body = "def shared():\n    x = 1\n    y = 2\n    return x + y\n"
    (tmp_path / "one.py").write_text(body)
    (tmp_path / "two.py").write_text(body)
    ranked = mod.handle("rank_examples", tmp_path, {"limit": 5, "depth": 2})
    assert ranked["ok"] is True
    assert ranked["count"] >= 1
    summary = mod.handle("pattern_summary", tmp_path, {"limit": 5, "depth": 2})
    assert "items" in summary
    assert summary["instance_count"] >= 1
