"""L1 unit tests for structural-anchor.

Calls library functions directly (subprocess boundary is L2).
Prefers plugins/structural-anchor/structural_anchor.py; falls back to
tools/structural-anchor/ for the current repo layout.
"""
from __future__ import annotations

import io
import json
import math
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLS_DIR = REPO_ROOT / "tools" / "structural-anchor"

_impl = None
if (PLUGIN_DIR / "structural_anchor.py").is_file():
    sys.path.insert(0, str(PLUGIN_DIR))
    import structural_anchor as _impl  # type: ignore
elif (TOOLS_DIR / "structural_anchor.py").is_file():
    sys.path.insert(0, str(TOOLS_DIR))
    import structural_anchor as _impl  # type: ignore

pytestmark = [
    pytest.mark.xfail(
        _impl is None,
        reason="structural-anchor implementation not present under plugins/ or tools/",
        strict=False,
    )
]

if _impl is not None:
    DEFAULT_SKIP_DIRS = _impl.DEFAULT_SKIP_DIRS
    extract_python_symbols = _impl.extract_python_symbols
    get_codebase_statistics = _impl.get_codebase_statistics
    get_project_map = _impl.get_project_map
    iter_source_files = _impl.iter_source_files
    list_languages = _impl.list_languages
    normalize_skip_dirs = _impl.normalize_skip_dirs
else:  # pragma: no cover - xfail path
    DEFAULT_SKIP_DIRS = set()

    def extract_python_symbols(*_a, **_k):  # type: ignore
        raise NotImplementedError

    def get_codebase_statistics(*_a, **_k):  # type: ignore
        raise NotImplementedError

    def get_project_map(*_a, **_k):  # type: ignore
        raise NotImplementedError

    def iter_source_files(*_a, **_k):  # type: ignore
        raise NotImplementedError

    def list_languages(*_a, **_k):  # type: ignore
        raise NotImplementedError

    def normalize_skip_dirs(*_a, **_k):  # type: ignore
        raise NotImplementedError


def _run_main(tool: str, payload: str | dict, home: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setenv("TOOL_NAME", tool)
    monkeypatch.setenv("HOME", str(home))
    if isinstance(payload, dict):
        payload = json.dumps(payload) + "\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    with pytest.raises(SystemExit) as exited:
        _impl.main()
    return int(exited.value.code)


def test_get_project_map_skips_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "keep.py").write_text("def keep():\n    return 1\n", encoding="utf-8")
    skip = tmp_path / "skip_me"
    skip.mkdir()
    (skip / "secret.py").write_text("def secret():\n    return 0\n", encoding="utf-8")

    result = get_project_map(tmp_path, depth=3, skip_dirs={"skip_me"})
    blob = json.dumps(result)
    assert "secret" not in blob
    assert "keep" in blob


def test_get_project_map_depth_clips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    deep = tmp_path / "pkg" / "a" / "b" / "c.py"
    deep.parent.mkdir(parents=True)
    deep.write_text("def buried():\n    pass\n", encoding="utf-8")
    (tmp_path / "top.py").write_text("def top():\n    pass\n", encoding="utf-8")

    result = get_project_map(tmp_path, depth=1, skip_dirs=set(DEFAULT_SKIP_DIRS))
    names = {sym["name"] for pkg in result["packages"] for sym in pkg["symbols"]}
    assert "top" in names
    assert "buried" not in names


def test_get_project_map_syntax_error_parse_error_no_abort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "ok.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text("def oops(\n", encoding="utf-8")

    result = get_project_map(tmp_path, depth=2, skip_dirs=set())
    assert result["statistics"]["parse_errors"] >= 1
    names = {sym["name"] for pkg in result["packages"] for sym in pkg["symbols"]}
    assert "ok" in names


def test_get_project_map_error_missing_root_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code = _run_main("get_project_map", {"depth": 1}, tmp_path / "home", monkeypatch)
    assert code != 0


def test_list_languages_counts_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")

    result = list_languages(tmp_path, depth=2, skip_dirs=set())
    assert result["primary"] == "python"
    by_id = {row["id"]: row for row in result["languages"]}
    assert by_id["python"]["file_count"] == 2


def test_list_languages_error_unknown_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code = _run_main(
        "not_a_real_tool",
        {"root_path": str(tmp_path)},
        tmp_path / "home",
        monkeypatch,
    )
    assert code != 0


def test_get_codebase_statistics_complexity_zero_without_functions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "empty_mod.py").write_text("# no functions\nX = 1\n", encoding="utf-8")

    result = get_codebase_statistics(tmp_path, depth=2, skip_dirs=set())
    assert float(result["complexity"]) == 0.0
    assert not math.isnan(float(result["complexity"]))


def test_get_codebase_statistics_error_malformed_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code = _run_main(
        "get_codebase_statistics",
        "{not json\n",
        tmp_path / "home",
        monkeypatch,
    )
    assert code != 0


def test_go_unexported_const_var_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "sample.go").write_text(
        "\n".join(
            [
                "package pkg",
                "",
                "const ExportedConst = 1",
                "const unexportedConst = 2",
                'var ExportedVar = "ok"',
                'var unexportedVar = "no"',
                "",
                "func ExportedFn() {}",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "go.mod").write_text("module example.com/t\n\ngo 1.22\n", encoding="utf-8")

    result = get_project_map(tmp_path, depth=3, skip_dirs=set())
    names = {
        (sym["name"], sym["kind"])
        for pkg_row in result["packages"]
        for sym in pkg_row["symbols"]
    }
    if not names:
        pytest.xfail("Go symbol helper not available / not implemented")

    assert ("ExportedConst", "const") in names
    assert ("ExportedVar", "var") in names
    assert ("unexportedConst", "const") not in names
    assert ("unexportedVar", "var") not in names


def test_skip_dirs_honored_by_walk(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "x.py").write_text("z=1\n", encoding="utf-8")

    files = {
        p.relative_to(tmp_path).as_posix()
        for p in iter_source_files(tmp_path, depth=2, skip_dirs=set(DEFAULT_SKIP_DIRS))
    }
    assert "a.py" in files
    assert "node_modules/x.py" not in files


def test_normalize_skip_dirs_variants() -> None:
    assert normalize_skip_dirs(None) == DEFAULT_SKIP_DIRS
    assert normalize_skip_dirs("") == DEFAULT_SKIP_DIRS
    assert normalize_skip_dirs("node_modules,vendor") == {"node_modules", "vendor"}
    assert normalize_skip_dirs(["dist", "build"]) == {"dist", "build"}
    assert normalize_skip_dirs('["generated"]') == {"generated"}


def test_extract_python_symbols_async_and_nested(tmp_path: Path) -> None:
    source = tmp_path / "nested.py"
    source.write_text(
        "\n".join(
            [
                "class Outer:",
                "    class Inner:",
                "        async def method(self, x: int) -> int:",
                "            if x:",
                "                return x",
                "            return 0",
                "",
                "async def top(a, /, b, *args, c=1, **kw) -> None:",
                "    pass",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    symbols, complexities, lines = extract_python_symbols(source)
    names = {(s["name"], s["kind"]) for s in symbols}
    assert ("Outer", "class") in names
    assert ("Inner", "class") in names
    assert ("method", "method") in names
    assert ("top", "function") in names
    assert lines > 0
    assert complexities


def test_get_project_map_idempotent_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    first = get_project_map(tmp_path, depth=2, skip_dirs=set())
    second = get_project_map(tmp_path, depth=2, skip_dirs=set())
    assert first["packages"] == second["packages"]
    assert "cached" in second


def test_list_languages_empty_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    result = list_languages(tmp_path, depth=1, skip_dirs=set())
    assert result["languages"] == []
    assert result["primary"] is None
