"""L1 unit tests for environment-validator."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "tools" / "environment-validator"
FIXTURES = REPO / "testing" / "fixtures"
sys.path.insert(0, str(TOOLS))
import environment_validator as mod  # noqa: E402


class _FakeStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)


def test_handle_empty() -> None:
    out = mod.handle("check_env_vars", FIXTURES / "empty", {"depth": 2})
    assert out["ok"] is True
    assert out["missing"] == []
    assert out["count"] == 0


def test_handle_py_small_parses_fixture_env() -> None:
    out = mod.handle("parse_env_files", FIXTURES / "py-small", {"depth": 3})
    # py-small ships .env.example with real keys only
    assert out["loaded"] is True
    keys = {v["key"] for v in out["vars"]}
    assert keys == {"DATABASE_URL", "APP_ENV", "API_KEY", "LOG_LEVEL"}
    assert all(v["path"] == ".env.example" for v in out["vars"])


def test_domain_env_roundtrip(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("APP_HOST=localhost\nAPP_PORT=8080\n", encoding="utf-8")
    (tmp_path / ".env").write_text("APP_HOST=127.0.0.1\nEXTRA_ONLY=1\n", encoding="utf-8")
    (tmp_path / "local.env").write_text("OTHER=9\n", encoding="utf-8")

    parsed = mod.handle("parse_env_files", tmp_path, {"depth": 2})
    keys = {v["key"] for v in parsed["vars"]}
    assert keys == {"APP_HOST", "APP_PORT", "EXTRA_ONLY", "OTHER"}
    assert all("path" in v for v in parsed["vars"])

    checked = mod.handle("check_env_vars", tmp_path, {"depth": 2})
    assert "APP_PORT" in checked["missing"]
    assert "EXTRA_ONLY" in checked["unused"]
    assert all(
        v["key"] in keys or v["key"] in checked["required"] for v in checked["violations"]
    )

    cmp = mod.handle("compare_env_templates", tmp_path, {"depth": 2})
    assert "APP_PORT" in cmp["missing"]
    assert "EXTRA_ONLY" in cmp["extra"]
    assert cmp["tool"] == "compare_env_templates"

    summary = mod.handle("env_summary", tmp_path, {"depth": 2})
    assert summary["count"] >= 2
    assert all("keys" in it and "path" in it for it in summary["items"])
    flat = {k for it in summary["items"] for k in it["keys"]}
    assert flat <= keys


def test_check_required_override(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("A=1\n", encoding="utf-8")
    out = mod.handle("check_env_vars", tmp_path, {"required": ["A", "B"], "depth": 1})
    assert out["missing"] == ["B"]
    assert out["ok"] is False


def test_no_invented_keys(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("REAL_KEY=1\n", encoding="utf-8")
    out = mod.handle("env_summary", tmp_path, {"depth": 1})
    for it in out["items"]:
        assert it["keys"] == ["REAL_KEY"]


def test_validate_traversal() -> None:
    with pytest.raises(SystemExit):
        mod.validate_root_path("/tmp/../etc")


def test_main_ok(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "check_env_vars")
    payload = {"root_path": str(FIXTURES / "empty"), "query": "x"}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    mod.main()
    out = json.loads(capsys.readouterr().out)
    assert isinstance(out, dict)
    assert "ok" in out


def test_main_missing_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "check_env_vars")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        mod.main()


def test_main_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "check_env_vars")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{bad\n"))
    with pytest.raises(SystemExit):
        mod.main()


def test_main_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "nope")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        mod.main()


def test_main_all_tools(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    for tool in ["check_env_vars", "parse_env_files", "compare_env_templates", "env_summary"]:
        monkeypatch.setenv("TOOL_NAME", tool)
        payload = {"root_path": str(FIXTURES / "py-small"), "depth": 3, "limit": 5}
        monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
        mod.main()
        out = json.loads(capsys.readouterr().out)
        assert isinstance(out, dict)


def test_iter_files() -> None:
    files = mod.iter_files(FIXTURES / "py-small", depth=3)
    assert any(p.name.endswith(".py") for p in files)


def test_main_too_large(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "check_env_vars")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{" + b"a" * (mod.MAX_INPUT_BYTES + 5)))
    with pytest.raises(SystemExit):
        mod.main()


def test_main_non_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "check_env_vars")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"[]\n"))
    with pytest.raises(SystemExit):
        mod.main()


def test_unknown_tool_handle() -> None:
    out = mod.handle("custom_op", FIXTURES / "empty", {})
    assert out.get("ok") is False
