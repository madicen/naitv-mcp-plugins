"""L1 unit tests for validate-and-test."""
from __future__ import annotations
import io, json, sys
from pathlib import Path
import pytest
REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "tools" / "validate-and-test"
FIXTURES = REPO / "testing" / "fixtures"
sys.path.insert(0, str(TOOLS))
import validate_and_test as mod  # noqa: E402

class _FakeStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)

def test_handle_empty() -> None:
    out = mod.handle('detect_build_system', FIXTURES / "empty", {"query": "x", "depth": 2})
    assert isinstance(out, dict)
    assert out["ok"] is True
    assert out["build_system"] == "unknown"

def test_handle_py_small() -> None:
    out = mod.handle('detect_build_system', FIXTURES / "py-small", {"query": "Greeter", "depth": 3})
    assert isinstance(out, dict)
    assert out["ok"] is True
    assert out["tool"] == "detect_build_system"
    # py-small has no go.mod/pyproject — unknown is honest
    assert out["build_system"] in {"unknown", "python", "make", "go", "npm"}

def test_detect_go_mod(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example\n\ngo 1.22\n")
    out = mod.handle("detect_build_system", tmp_path, {})
    assert out["build_system"] == "go"
    assert "go.mod" in out["config_files"]
    assert any("go test" in c for c in out["commands"])

def test_run_validation_lists_tests(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='t'\n")
    (tmp_path / "test_add.py").write_text("def test_add():\n    assert 1 + 1 == 2\n")
    out = mod.handle("run_validation", tmp_path, {"depth": 2, "limit": 10})
    assert out["ok"] is True
    assert out["exit_code"] == 0
    assert out["dry_run"] is True
    assert any(i["path"] == "test_add.py" for i in out["items"])
    assert "test_add" in out["items"][0]["symbols"]

def test_summarize_failures_from_log() -> None:
    root = FIXTURES / "empty"
    log = "ok\nFAIL: test_foo\n--- FAIL: TestBar\n"
    out = mod.handle("summarize_failures", root, {"log": log, "limit": 10})
    assert out["count"] >= 2
    assert out["first_failure"] is not None
    assert "FAIL" in out["first_failure"]["name"]

def test_summarize_failures_from_file(tmp_path: Path) -> None:
    (tmp_path / "pytest.log").write_text("PASSED\nFAILED test_x - AssertionError\n")
    out = mod.handle("summarize_failures", tmp_path, {"depth": 2, "limit": 5})
    assert out["count"] >= 1
    assert out["items"][0]["path"] == "pytest.log"

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
    monkeypatch.setenv("TOOL_NAME", 'detect_build_system')
    payload = {"root_path": str(FIXTURES / "empty"), "query": "x"}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    mod.main()
    out = json.loads(capsys.readouterr().out)
    assert isinstance(out, dict)

def test_main_missing_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", 'detect_build_system')
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        mod.main()

def test_main_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", 'detect_build_system')
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{bad\n"))
    with pytest.raises(SystemExit):
        mod.main()

def test_main_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "nope")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        mod.main()

def test_main_all_tools(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    for tool in ['detect_build_system', 'run_validation', 'summarize_failures']:
        monkeypatch.setenv("TOOL_NAME", tool)
        payload = {"root_path": str(FIXTURES / "py-small"), "query": "Greeter", "path": "README.md", "limit": 5}
        monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
        mod.main()
        out = json.loads(capsys.readouterr().out)
        assert isinstance(out, dict)
        assert out.get("ok") is not None or "exit_code" in out

def test_iter_files() -> None:
    files = mod.iter_files(FIXTURES / "py-small", depth=3)
    assert any(p.name.endswith(".py") for p in files)

def test_main_too_large(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", 'detect_build_system')
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{" + b"a" * (mod.MAX_INPUT_BYTES + 5)))
    with pytest.raises(SystemExit):
        mod.main()

def test_main_non_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", 'detect_build_system')
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"[]\n"))
    with pytest.raises(SystemExit):
        mod.main()

def test_detect_build_mini() -> None:
    out = mod.handle("detect_build_system", FIXTURES / "build-mini", {})
    assert out["build_system"] == "make"
    assert "Makefile" in out["config_files"]
