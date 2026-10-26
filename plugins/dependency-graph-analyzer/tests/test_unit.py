"""L1: dependency-graph-analyzer tools."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "tools" / "dependency-graph-analyzer"
FIXTURES = REPO / "testing" / "fixtures"

sys.path.insert(0, str(TOOLS))
import dependency_graph_analyzer as dga  # noqa: E402


class _FakeStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)


def test_build_graph_deps_mini() -> None:
    out = dga.build_graph(FIXTURES / "deps-mini", language="python")
    assert "mod_a" in out["nodes"]
    assert "mod_c" in out["nodes"]
    pairs = {(e["from"], e["to"]) for e in out["edges"]}
    assert ("mod_a", "mod_b") in pairs
    assert ("mod_a", "mod_c") in pairs
    assert ("mod_b", "mod_c") in pairs


def test_query_mod_a() -> None:
    out = dga.query_dependencies(FIXTURES / "deps-mini", "mod_a")
    assert out["found"] is True
    assert "mod_b" in out["imports"]
    assert "mod_c" in out["imports"]


def test_find_hubs() -> None:
    out = dga.find_hubs(FIXTURES / "deps-mini", limit=3)
    assert out["modules"][0]["module"] == "mod_c"
    assert out["modules"][0]["fan_in"] >= 2


def test_export_dot() -> None:
    out = dga.export_graph(FIXTURES / "deps-mini", fmt="dot")
    assert out["format"] == "dot"
    assert "digraph" in out["graph"]
    assert "mod_a" in out["graph"]


def test_empty_graph() -> None:
    out = dga.build_graph(FIXTURES / "empty")
    assert out["nodes"] == []
    assert out["edges"] == []


def test_validate_root_rejects_traversal() -> None:
    with pytest.raises(SystemExit):
        dga.validate_root_path("/tmp/../etc")


def test_main_build(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "build_import_graph")
    payload = {"root_path": str(FIXTURES / "deps-mini"), "language": "python"}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    dga.main()
    out = json.loads(capsys.readouterr().out)
    assert out["edge_count"] >= 3


def test_main_query(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "query_dependencies")
    payload = {"root_path": str(FIXTURES / "deps-mini"), "module": "mod_c"}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    dga.main()
    out = json.loads(capsys.readouterr().out)
    assert "mod_a" in out["imported_by"]


def test_main_hubs(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "find_hubs")
    payload = {"root_path": str(FIXTURES / "deps-mini"), "limit": 2}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    dga.main()
    out = json.loads(capsys.readouterr().out)
    assert out["count"] == 2


def test_main_export(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "export_graph")
    payload = {"root_path": str(FIXTURES / "deps-mini"), "format": "json"}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    dga.main()
    out = json.loads(capsys.readouterr().out)
    assert out["format"] == "json"
    assert "nodes" in out["graph"]


def test_main_missing_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "query_dependencies")
    payload = {"root_path": str(FIXTURES / "deps-mini")}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    with pytest.raises(SystemExit):
        dga.main()


def test_main_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "build_import_graph")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{bad\n"))
    with pytest.raises(SystemExit):
        dga.main()


def test_main_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "nope")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        dga.main()


def test_bad_export_format() -> None:
    with pytest.raises(SystemExit):
        dga.export_graph(FIXTURES / "deps-mini", fmt="xml")


def test_go_small_graph() -> None:
    out = dga.build_graph(FIXTURES / "go-small", language="go")
    assert out["language"] == "go"
    assert "pkg/greeter" in out["nodes"]


def test_py_imports_syntax_error() -> None:
    assert dga._py_imports("def (\n") == []


def test_go_imports_block_and_single() -> None:
    text = 'package main\nimport (\n\t"fmt"\n\t"os"\n)\nimport "net/http"\n'
    got = dga._go_imports(text)
    assert "fmt" in got and "os" in got and "net/http" in got


def test_module_name_init(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    init = pkg / "__init__.py"
    init.write_text("x = 1\n")
    assert dga.module_name_for(init, tmp_path, "python") == "pkg"


def test_validate_root_missing(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        dga.validate_root_path(str(tmp_path / "nope"))


def test_validate_root_file(tmp_path: Path) -> None:
    f = tmp_path / "f.txt"
    f.write_text("x")
    with pytest.raises(SystemExit):
        dga.validate_root_path(str(f))


def test_main_input_too_large(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "build_import_graph")
    big = b"{" + (b"a" * (dga.MAX_INPUT_BYTES + 10))
    monkeypatch.setattr(sys, "stdin", _FakeStdin(big))
    with pytest.raises(SystemExit):
        dga.main()


def test_main_non_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "build_import_graph")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"[]\n"))
    with pytest.raises(SystemExit):
        dga.main()


def test_main_bad_root_type(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "build_import_graph")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b'{"root_path": 1}\n'))
    with pytest.raises(SystemExit):
        dga.main()


def test_skip_dirs_and_depth(tmp_path: Path) -> None:
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.py").write_text("import y\n")
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    (deep / "z.py").write_text("import z\n")
    (tmp_path / "top.py").write_text("import os\n")
    files = dga.iter_source_files(tmp_path, depth=0, language="python")
    names = {p.name for p in files}
    assert "top.py" in names
    assert "x.py" not in names
    assert "z.py" not in names
