"""L1: build-system-integrator tools."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "tools" / "build-system-integrator"
FIXTURES = REPO / "testing" / "fixtures"

sys.path.insert(0, str(TOOLS))
import build_system_integrator as bsi  # noqa: E402


class _FakeStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)


def test_detect_make() -> None:
    out = bsi.detect_build_tool(FIXTURES / "build-mini")
    assert out["tool"] == "make"
    assert "Makefile" in out["config_files"]


def test_detect_go() -> None:
    out = bsi.detect_build_tool(FIXTURES / "go-small")
    assert out["tool"] == "go"


def test_detect_empty() -> None:
    out = bsi.detect_build_tool(FIXTURES / "empty")
    assert out == {"tool": "unknown", "config_files": []}


def test_list_make_targets() -> None:
    out = bsi.list_build_targets(FIXTURES / "build-mini")
    assert out["tool"] == "make"
    assert "hello" in out["targets"]
    assert "all" in out["targets"]


def test_run_hello() -> None:
    out = bsi.run_build_target(FIXTURES / "build-mini", "hello")
    assert out["exit_code"] == 0
    assert "hello-from-make" in out["output_tail"]


def test_run_unknown_target() -> None:
    out = bsi.run_build_target(FIXTURES / "build-mini", "nope-target")
    # make may still run and fail; allowlisted name passes through to make
    assert "exit_code" in out
    assert out["target"] == "nope-target"


def test_parse_errors() -> None:
    out = bsi.parse_build_errors("pkg/main.go:3:1: undefined: Missing\nnoise\n")
    assert out["count"] == 1
    assert out["errors"][0]["file"] == "pkg/main.go"
    assert out["errors"][0]["line"] == 3


def test_validate_root_rejects_traversal() -> None:
    with pytest.raises(SystemExit):
        bsi.validate_root_path("/tmp/../etc")


def test_validate_root_rejects_missing(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        bsi.validate_root_path(str(tmp_path / "missing"))


def test_main_detect(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "detect_build_tool")
    payload = {"root_path": str(FIXTURES / "build-mini")}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    bsi.main()
    out = json.loads(capsys.readouterr().out)
    assert out["tool"] == "make"


def test_main_parse_requires_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "parse_build_errors")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        bsi.main()


def test_main_run_requires_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "run_build_target")
    payload = {"root_path": str(FIXTURES / "build-mini")}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    with pytest.raises(SystemExit):
        bsi.main()


def test_main_list(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "list_build_targets")
    payload = {"root_path": str(FIXTURES / "go-small")}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    bsi.main()
    out = json.loads(capsys.readouterr().out)
    assert out["targets"] == ["build", "test", "vet"]


def test_main_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "detect_build_tool")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{bad\n"))
    with pytest.raises(SystemExit):
        bsi.main()


def test_run_on_empty() -> None:
    out = bsi.run_build_target(FIXTURES / "empty", "hello")
    assert out["exit_code"] == 2
    assert out["tool"] == "unknown"


def test_npm_and_cargo_targets(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"lint": "echo", "test": "echo"}}), encoding="utf-8"
    )
    out = bsi.list_build_targets(tmp_path)
    assert out["tool"] == "npm"
    assert out["targets"] == ["lint", "test"]
    assert bsi._cmd_for_target("npm", "lint") == ["npm", "run", "lint", "--if-present"]
    assert bsi._cmd_for_target("npm", "bad target") is None

    cargo = tmp_path / "cargo-root"
    cargo.mkdir()
    (cargo / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    out2 = bsi.list_build_targets(cargo)
    assert out2["tool"] == "cargo"
    assert out2["targets"] == ["build", "test", "check"]
    assert bsi._cmd_for_target("cargo", "check") == ["cargo", "check"]


def test_python_marker(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    out = bsi.detect_build_tool(tmp_path)
    assert out["tool"] == "python"
    assert bsi.list_build_targets(tmp_path)["targets"] == ["pytest"]
    assert bsi._cmd_for_target("python", "pytest")[0] == "python3"


def test_run_go_build() -> None:
    out = bsi.run_build_target(FIXTURES / "go-small", "build", timeout=30.0)
    assert out["tool"] == "go"
    assert out["target"] == "build"
    assert isinstance(out["exit_code"], int)


def test_run_command_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")

    def boom(*_a, **_k):
        raise FileNotFoundError(2, "missing", "make")

    monkeypatch.setattr(bsi.subprocess, "run", boom)
    out = bsi.run_build_target(tmp_path, "all")
    assert out["exit_code"] == 127


def test_run_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")

    def boom(*_a, **_k):
        raise bsi.subprocess.TimeoutExpired(cmd=["make"], timeout=0.1)

    monkeypatch.setattr(bsi.subprocess, "run", boom)
    out = bsi.run_build_target(tmp_path, "all")
    assert out["exit_code"] == 124


def test_main_run_and_parse(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TOOL_NAME", "run_build_target")
    payload = {"root_path": str(FIXTURES / "build-mini"), "target": "hello"}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    bsi.main()
    out = json.loads(capsys.readouterr().out)
    assert out["exit_code"] == 0

    monkeypatch.setenv("TOOL_NAME", "parse_build_errors")
    monkeypatch.setattr(
        sys,
        "stdin",
        _FakeStdin((json.dumps({"output": "f.go:1: msg"}) + "\n").encode()),
    )
    bsi.main()
    out2 = json.loads(capsys.readouterr().out)
    assert out2["count"] == 1


def test_main_unknown_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "nope")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        bsi.main()


def test_main_non_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "detect_build_tool")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"[1]\n"))
    with pytest.raises(SystemExit):
        bsi.main()


def test_bad_npm_json(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{bad", encoding="utf-8")
    assert bsi._npm_targets(tmp_path) == []
