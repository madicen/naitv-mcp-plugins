"""L1 unit tests for change-impact-analyzer."""
from __future__ import annotations
import io, json, sys
from pathlib import Path
import pytest
REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "tools" / "change-impact-analyzer"
FIXTURES = REPO / "testing" / "fixtures"
sys.path.insert(0, str(TOOLS))
import change_impact_analyzer as mod  # noqa: E402

class _FakeStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)

def test_handle_empty() -> None:
    out = mod.handle('analyze_change_impact', FIXTURES / "empty", {"query": "x", "depth": 2})
    assert isinstance(out, dict)

def test_handle_py_small() -> None:
    out = mod.handle('analyze_change_impact', FIXTURES / "py-small", {"query": "Greeter", "depth": 3})
    assert isinstance(out, dict)

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
    monkeypatch.setenv("TOOL_NAME", 'analyze_change_impact')
    payload = {"root_path": str(FIXTURES / "empty"), "query": "x"}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    mod.main()
    out = json.loads(capsys.readouterr().out)
    assert isinstance(out, dict)

def test_main_missing_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", 'analyze_change_impact')
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        mod.main()

def test_main_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", 'analyze_change_impact')
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{bad\n"))
    with pytest.raises(SystemExit):
        mod.main()

def test_main_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "nope")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        mod.main()

def test_main_all_tools(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    for tool in ['analyze_change_impact', 'list_affected_tests', 'affected_modules', 'impact_summary']:
        monkeypatch.setenv("TOOL_NAME", tool)
        payload = {"root_path": str(FIXTURES / "py-small"), "query": "Greeter", "path": "README.md", "limit": 5}
        monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
        mod.main()
        out = json.loads(capsys.readouterr().out)
        assert isinstance(out, dict)

def test_iter_files() -> None:
    files = mod.iter_files(FIXTURES / "py-small", depth=3)
    assert any(p.name.endswith(".py") for p in files)

def test_main_too_large(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", 'analyze_change_impact')
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{" + b"a" * (mod.MAX_INPUT_BYTES + 5)))
    with pytest.raises(SystemExit):
        mod.main()

def test_main_non_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", 'analyze_change_impact')
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"[]\n"))
    with pytest.raises(SystemExit):
        mod.main()
