import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]  # naitv-mcp-plugins root
sys.path.insert(0, str(ROOT))
from structural_anchor import build_project_map


def _run(tool: str, payload: dict, env_home: str | None = None):
    env = os.environ.copy()
    env["TOOL_NAME"] = tool
    if env_home:
        env["HOME"] = env_home
    return subprocess.run(
        [sys.executable, str(ROOT / "structural_anchor.py")],
        input=json.dumps(payload) + "\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_this_repo_map(tmp_path: Path):
    p1 = _run("get_project_map", {"root_path": str(REPO), "depth": 4}, env_home=str(tmp_path))
    assert p1.returncode == 0, p1.stderr
    out1 = json.loads(p1.stdout)
    assert out1["cached"] is False
    assert isinstance(out1["packages"], list)


def test_perf_smoke_many_tiny_files(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    tree = tmp_path / "tree"
    tree.mkdir()
    for i in range(500):
        d = tree / f"p{i % 50}"
        d.mkdir(exist_ok=True)
        (d / f"f{i}.py").write_text(f"def f{i}():\n    return {i}\n")
    t0 = time.perf_counter()
    proc = _run("get_project_map", {"root_path": str(tree), "depth": 5}, env_home=str(home))
    elapsed = time.perf_counter() - t0
    assert proc.returncode == 0, proc.stderr
    assert elapsed < 5.0  # soft CI budget; design target <2s on prune-heavy 50k


def test_mixed_language_directory_is_one_package(monkeypatch, tmp_path: Path):
    (tmp_path / "sample.py").write_text("def PythonSymbol():\n    pass\n")
    (tmp_path / "sample.go").write_text("package mixed\n\nfunc GoSymbol() {}\n")
    helper = tmp_path / "go-symbols"
    helper.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "request = json.load(sys.stdin)\n"
        "json.dump({'packages': [{'name': 'mixed',"
        " 'path': os.path.dirname(request['files'][0]),"
        " 'symbols': [{'name': 'GoSymbol', 'kind': 'function',"
        " 'signature': 'func GoSymbol()', 'line': 3}]}],"
        " 'func_complexity': [1], 'errors': 0}, sys.stdout)\n"
    )
    helper.chmod(0o755)
    monkeypatch.setattr("structural_anchor.ensure_go_symbols_bin", lambda _src: helper)

    project_map = build_project_map(tmp_path, 3, set())

    assert len(project_map["packages"]) == 1
    assert {symbol["name"] for symbol in project_map["packages"][0]["symbols"]} == {
        "PythonSymbol",
        "GoSymbol",
    }
