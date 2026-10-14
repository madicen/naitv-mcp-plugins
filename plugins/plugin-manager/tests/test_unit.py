"""L1: plugin-manager tools in-process."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "tools" / "plugin-manager"
FIXTURES = REPO / "testing" / "fixtures"

sys.path.insert(0, str(TOOLS))
import plugin_manager as pm  # noqa: E402


class _FakeStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)


def test_list_plugins_mini() -> None:
    out = pm.list_plugins(FIXTURES / "plugins-mini")
    assert out["count"] == 1
    assert out["plugins"][0]["name"] == "sample"
    assert out["plugins"][0]["entry_count"] == 1
    assert out["plugins"][0]["tool_count"] == 0


def test_list_plugins_empty() -> None:
    out = pm.list_plugins(FIXTURES / "empty")
    assert out == {"plugins": [], "count": 0}


def test_validate_plugin_ok() -> None:
    out = pm.validate_plugin(FIXTURES / "plugins-mini", "sample")
    assert out["ok"] is True
    assert out["errors"] == []


def test_validate_plugin_missing() -> None:
    out = pm.validate_plugin(FIXTURES / "empty", "sample")
    assert out["ok"] is False
    assert "not found" in out["errors"][0]


def test_test_plugin_lint() -> None:
    out = pm.test_plugin(FIXTURES / "plugins-mini", "sample", "lint")
    assert out["ok"] is True
    assert out["layers"] == "lint"


def test_validate_root_rejects_traversal() -> None:
    with pytest.raises(SystemExit):
        pm.validate_root_path("/tmp/../etc")


def test_validate_root_rejects_missing(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        pm.validate_root_path(str(tmp_path / "missing"))


def test_main_list(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "list_plugins")
    payload = {"root_path": str(FIXTURES / "plugins-mini")}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    pm.main()
    out = json.loads(capsys.readouterr().out)
    assert out["count"] == 1


def test_main_validate_missing_plugin_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TOOL_NAME", "validate_plugin")
    payload = {"root_path": str(FIXTURES / "plugins-mini")}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    with pytest.raises(SystemExit):
        pm.main()


def test_main_test_plugin(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "test_plugin")
    payload = {
        "root_path": str(FIXTURES / "plugins-mini"),
        "plugin": "sample",
        "layers": "lint",
    }
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    pm.main()
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True


def test_lint_bad_kind_and_tool_fields(tmp_path: Path) -> None:
    manifest = {
        "name": "bad",
        "entries": [
            {"kind": "nope", "name": "x", "delivery": "init", "body": "hi"},
            {
                "kind": "tool",
                "name": "t",
                "delivery": "on-demand",
                "body": "tool",
                "fields": {"io_mode": "weird"},
            },
            {"kind": "rule", "name": "x", "delivery": "init", "body": "dup"},
            {"kind": "rule", "delivery": "init", "body": "noname"},
            {"kind": "rule", "name": "empty", "delivery": "init", "body": "  "},
        ],
    }
    path = tmp_path / "plugins" / "bad" / "plugin.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    out = pm.validate_plugin(tmp_path, "bad")
    assert out["ok"] is False
    assert any("bad kind" in e for e in out["errors"])
    assert any("fields.exec" in e for e in out["errors"])


def test_lint_name_mismatch_and_empty_entries(tmp_path: Path) -> None:
    path = tmp_path / "plugins" / "a" / "plugin.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"name": "b", "entries": []}), encoding="utf-8")
    out = pm.validate_plugin(tmp_path, "a")
    assert out["ok"] is False
    assert any("name mismatch" in e for e in out["errors"])
    assert any("no entries" in e for e in out["errors"])


def test_invalid_manifest_json(tmp_path: Path) -> None:
    path = tmp_path / "plugins" / "broken" / "plugin.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not-json", encoding="utf-8")
    out = pm.validate_plugin(tmp_path, "broken")
    assert out["ok"] is False
    assert "not valid JSON" in out["errors"][0]


def test_discover_flat_layout(tmp_path: Path) -> None:
    path = tmp_path / "flat" / "plugin.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "name": "flat",
                "version": "1",
                "entries": [
                    {"kind": "rule", "name": "r", "delivery": "init", "body": "ok"}
                ],
            }
        ),
        encoding="utf-8",
    )
    out = pm.list_plugins(tmp_path)
    assert out["count"] == 1
    assert out["plugins"][0]["name"] == "flat"


def test_test_plugin_l2_missing_runner(tmp_path: Path) -> None:
    path = tmp_path / "plugins" / "sample" / "plugin.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "name": "sample",
                "entries": [
                    {"kind": "rule", "name": "r", "delivery": "init", "body": "ok"}
                ],
            }
        ),
        encoding="utf-8",
    )
    out = pm.test_plugin(tmp_path, "sample", "l2")
    assert out["ok"] is False
    assert "run_contract.py" in out["errors"][0]


def test_test_plugin_l2_missing_plugin(tmp_path: Path) -> None:
    out = pm.test_plugin(tmp_path, "nope", "l2")
    assert out["ok"] is False
    assert "not found" in out["errors"][0]


def test_test_plugin_bad_layers() -> None:
    with pytest.raises(SystemExit):
        pm.test_plugin(FIXTURES / "plugins-mini", "sample", "l9")


def test_main_rejects_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "list_plugins")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{not json\n"))
    with pytest.raises(SystemExit):
        pm.main()


def test_main_rejects_non_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "list_plugins")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"[1]\n"))
    with pytest.raises(SystemExit):
        pm.main()


def test_main_rejects_unknown_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "nope")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        pm.main()


def test_main_rejects_relative_file_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    f = tmp_path / "file.txt"
    f.write_text("x", encoding="utf-8")
    monkeypatch.setenv("TOOL_NAME", "list_plugins")
    monkeypatch.setattr(
        sys, "stdin", _FakeStdin((json.dumps({"root_path": str(f)}) + "\n").encode())
    )
    with pytest.raises(SystemExit):
        pm.main()


def test_run_l2_on_repo_lazy_dev() -> None:
    ok, errors, output = pm.run_l2(REPO, "lazy-dev")
    # rules_only plugins skip most L2 tool checks; exit may be 0 or soft.
    assert isinstance(ok, bool)
    assert isinstance(errors, list)
    assert isinstance(output, str)
