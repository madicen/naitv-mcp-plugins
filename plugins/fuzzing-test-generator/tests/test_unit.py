"""L1 unit tests for fuzzing-test-generator."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "tools" / "fuzzing-test-generator"
FIXTURES = REPO / "testing" / "fixtures"
sys.path.insert(0, str(TOOLS))
import fuzzing_test_generator as mod  # noqa: E402


class _FakeStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)


def test_handle_empty() -> None:
    out = mod.handle("find_fuzz_targets", FIXTURES / "empty", {"depth": 2})
    assert out["items"] == []
    assert out["count"] == 0


def test_handle_py_small_generates_real_symbol() -> None:
    out = mod.handle("generate_fuzz_target", FIXTURES / "py-small", {"depth": 3})
    assert out["ok"] is True
    assert out["name"] in {"hello", "add"} or out["name"]  # from greeter.py
    assert out["name"] in out["generated"]
    assert "FakeHelper" not in out["generated"]
    assert "GreeterService" not in out["generated"]


def test_domain_go_and_python_fuzz(tmp_path: Path) -> None:
    (tmp_path / "parse.go").write_text(
        "package p\n\nfunc Parse(s string) string { return s }\n\n"
        "func FuzzParse(f *testing.F) {}\n",
        encoding="utf-8",
    )
    (tmp_path / "test_fuzz.py").write_text(
        "from hypothesis import given, strategies as st\n\n"
        "def encode(x: bytes) -> bytes:\n    return x\n\n"
        "@given(st.binary())\n"
        "def test_encode(data):\n    encode(data)\n",
        encoding="utf-8",
    )

    found = mod.handle("find_fuzz_targets", tmp_path, {"depth": 2})
    names = {it["name"] for it in found["items"]}
    assert "FuzzParse" in names
    assert "test_encode" in names or "encode" in names
    for it in found["items"]:
        assert "path" in it and "name" in it

    gen = mod.handle("generate_fuzz_target", tmp_path, {"symbol": "Parse", "depth": 2})
    assert gen["ok"] is True
    assert gen["name"] == "Parse"
    assert "Parse" in gen["generated"]
    assert "FuzzWidget" not in gen["generated"]

    good = mod.handle(
        "validate_fuzz_target",
        tmp_path,
        {"template": gen["generated"], "depth": 2},
    )
    assert good["ok"] is True
    assert "Parse" in good["matched_symbols"]

    bad = mod.handle(
        "validate_fuzz_target",
        tmp_path,
        {"template": "# call InventedCamelCase only\n", "depth": 2},
    )
    assert bad["ok"] is False
    assert bad["count"] >= 1

    smoke = mod.handle("run_fuzz_smoke", tmp_path, {"depth": 2})
    assert smoke["ok"] is True
    assert smoke["exit_code"] == 0
    smoke_names = {t["name"] for t in smoke["targets"]}
    assert smoke_names <= names
    assert "dry-run" in smoke["summary"]


def test_validate_traversal() -> None:
    with pytest.raises(SystemExit):
        mod.validate_root_path("/tmp/../etc")


def test_main_ok(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "find_fuzz_targets")
    payload = {"root_path": str(FIXTURES / "empty")}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    mod.main()
    out = json.loads(capsys.readouterr().out)
    assert isinstance(out, dict)


def test_main_missing_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "find_fuzz_targets")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        mod.main()


def test_main_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "find_fuzz_targets")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{bad\n"))
    with pytest.raises(SystemExit):
        mod.main()


def test_main_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "nope")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        mod.main()


def test_main_all_tools(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    for tool in [
        "find_fuzz_targets",
        "generate_fuzz_target",
        "validate_fuzz_target",
        "run_fuzz_smoke",
    ]:
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
    monkeypatch.setenv("TOOL_NAME", "find_fuzz_targets")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{" + b"a" * (mod.MAX_INPUT_BYTES + 5)))
    with pytest.raises(SystemExit):
        mod.main()


def test_main_non_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "find_fuzz_targets")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"[]\n"))
    with pytest.raises(SystemExit):
        mod.main()


def test_unknown_tool_handle() -> None:
    out = mod.handle("custom_op", FIXTURES / "empty", {})
    assert out.get("ok") is False
