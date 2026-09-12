import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(root: Path, tool: str, home: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["TOOL_NAME"] = tool
    return subprocess.run(
        [sys.executable, str(ROOT / "structural_anchor.py")],
        input=json.dumps({"root_path": str(root), "depth": 5}) + "\n",
        capture_output=True,
        text=True,
        env=env,
    )


def test_get_project_map_cli_and_cache_hit(tmp_path: Path):
    root = tmp_path / "project"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "m.py").write_text("def f():\n    return 1\n")
    home = tmp_path / "home"

    first = run_cli(root, "get_project_map", home)
    second = run_cli(root, "get_project_map", home)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert json.loads(first.stdout)["cached"] is False
    out = json.loads(second.stdout)
    assert "packages" in out and "statistics" in out
    assert out["cached"] is True


def test_list_languages_and_statistics_shapes(tmp_path: Path):
    (tmp_path / "m.py").write_text("def f():\n    return 1\n")
    home = tmp_path / "home"

    languages_proc = run_cli(tmp_path, "list_languages", home)
    statistics_proc = run_cli(tmp_path, "get_codebase_statistics", home)

    assert languages_proc.returncode == 0, languages_proc.stderr
    languages = json.loads(languages_proc.stdout)
    assert languages["languages"] == [{"id": "python", "file_count": 1, "line_count": 2}]
    assert languages["primary"] == "python"

    assert statistics_proc.returncode == 0, statistics_proc.stderr
    statistics = json.loads(statistics_proc.stdout)
    assert {
        "total_files",
        "total_lines",
        "complexity",
        "packages",
        "parse_errors",
        "by_language",
    } <= statistics.keys()
    assert statistics["by_language"]["python"] == {
        "files": 1,
        "lines": 2,
        "complexity": 1.0,
    }


def test_unknown_tool_name_exits_nonzero(tmp_path: Path):
    proc = run_cli(tmp_path, "unknown_tool", tmp_path / "home")

    assert proc.returncode != 0
    assert "unknown or missing TOOL_NAME" in proc.stderr


def test_unparseable_python_contributes_to_total_lines(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("def b():\n    return 1\n")
    (tmp_path / "broken.py").write_text("def broken(:\n    pass\n    pass\n")

    proc = run_cli(tmp_path, "get_codebase_statistics", tmp_path / "home")

    assert proc.returncode == 0, proc.stderr
    statistics = json.loads(proc.stdout)
    assert statistics["total_files"] == 3
    assert statistics["total_lines"] == 6
    assert statistics["parse_errors"] == 1
    assert statistics["by_language"]["python"]["lines"] == 6
