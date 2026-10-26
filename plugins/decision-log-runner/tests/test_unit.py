"""L1 unit tests for decision-log-runner."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "tools" / "decision-log-runner"
FIXTURES = REPO / "testing" / "fixtures"
sys.path.insert(0, str(TOOLS))
import decision_log_runner as mod  # noqa: E402


class _FakeStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)


def test_handle_empty() -> None:
    out = mod.handle("parse_decision_log", FIXTURES / "empty", {"depth": 2})
    assert out["loaded"] is False
    assert out["decisions"] == []


def test_handle_py_small_no_adr() -> None:
    out = mod.handle("search_decisions", FIXTURES / "py-small", {"query": "Greeter", "depth": 3})
    assert out["items"] == []
    assert out["count"] == 0


def test_domain_decisions(tmp_path: Path) -> None:
    docs = tmp_path / "docs" / "adr"
    docs.mkdir(parents=True)
    (docs / "0001-use-sqlite.md").write_text(
        "# ADR-0001: Use sqlite\n\nStatus: Accepted\n\nStore data in sqlite.\n",
        encoding="utf-8",
    )
    (docs / "0002-use-sqlite.md").write_text(
        "# ADR-0002: Use sqlite\n\nStatus: Rejected\n",
        encoding="utf-8",
    )
    (tmp_path / "DECISIONS.md").write_text(
        "# Prefer local cache\n\nStatus: Proposed\n",
        encoding="utf-8",
    )
    dec_dir = tmp_path / "decisions"
    dec_dir.mkdir()
    (dec_dir / "ship-json.md").write_text(
        "## Decision: Ship JSON I/O\n\n- Status: accepted\n",
        encoding="utf-8",
    )

    parsed = mod.handle("parse_decision_log", tmp_path, {"depth": 4})
    assert parsed["loaded"] is True
    titles = {d["title"] for d in parsed["decisions"]}
    assert "Use sqlite" in titles
    assert "Prefer local cache" in titles
    assert "Ship JSON I/O" in titles
    ids = {d["id"] for d in parsed["decisions"]}
    assert "0001" in ids and "0002" in ids
    for d in parsed["decisions"]:
        assert d["path"]  # structured path
        assert (tmp_path / d["path"]).is_file()

    search = mod.handle("search_decisions", tmp_path, {"query": "sqlite", "depth": 4})
    assert search["count"] >= 2
    assert all("sqlite" in it["title"].lower() for it in search["items"])

    conflicts = mod.handle("check_decision_conflicts", tmp_path, {"depth": 4})
    assert conflicts["ok"] is False
    assert conflicts["count"] >= 1
    assert any(v["rule"] == "contradictory_status" for v in conflicts["violations"])
    for rid in conflicts["related_ids"]:
        assert rid in ids

    summary = mod.handle("summarize_decisions", tmp_path, {"topic": "sqlite", "depth": 4})
    assert summary["ok"] is True
    assert all(t in titles for t in summary["titles"])
    assert "FakeDecision" not in summary["summary"]


def test_no_invented_ids(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "adr-9-only.md").write_text(
        "# Only Real Title\nStatus: accepted\n", encoding="utf-8"
    )
    out = mod.handle("parse_decision_log", tmp_path, {"depth": 3})
    assert len(out["decisions"]) == 1
    d = out["decisions"][0]
    assert d["title"] == "Only Real Title"
    assert d["id"] in {"9", "adr-9-only"}


def test_validate_traversal() -> None:
    with pytest.raises(SystemExit):
        mod.validate_root_path("/tmp/../etc")


def test_main_ok(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "parse_decision_log")
    payload = {"root_path": str(FIXTURES / "empty")}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    mod.main()
    out = json.loads(capsys.readouterr().out)
    assert isinstance(out, dict)


def test_main_missing_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "parse_decision_log")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        mod.main()


def test_main_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "parse_decision_log")
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
        "parse_decision_log",
        "search_decisions",
        "check_decision_conflicts",
        "summarize_decisions",
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
    monkeypatch.setenv("TOOL_NAME", "parse_decision_log")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{" + b"a" * (mod.MAX_INPUT_BYTES + 5)))
    with pytest.raises(SystemExit):
        mod.main()


def test_main_non_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "parse_decision_log")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"[]\n"))
    with pytest.raises(SystemExit):
        mod.main()


def test_unknown_tool_handle() -> None:
    out = mod.handle("custom_op", FIXTURES / "empty", {})
    assert out.get("ok") is False
