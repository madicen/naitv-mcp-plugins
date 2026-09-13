# tools/symbol-navigator/tests/test_walk.py
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from symbol_navigator import iter_source_files, normalize_skip_dirs, DEFAULT_SKIP_DIRS


def test_normalize_skip_dirs_accepts_comma_string_and_list():
    assert normalize_skip_dirs("node_modules,vendor") == {"node_modules", "vendor"}
    assert normalize_skip_dirs(["dist", "build"]) == {"dist", "build"}
    assert normalize_skip_dirs(None) == DEFAULT_SKIP_DIRS
    assert normalize_skip_dirs("") == DEFAULT_SKIP_DIRS
    # must NOT be char-split
    assert "n" not in normalize_skip_dirs("node_modules")


def test_iter_respects_depth_and_extensions(tmp_path: Path):
    (tmp_path / "a.py").write_text("x=1\n")
    (tmp_path / "b.go").write_text("package main\n")
    (tmp_path / "c.txt").write_text("nope\n")
    deep = tmp_path / "d1" / "d2" / "d3"
    deep.mkdir(parents=True)
    (deep / "deep.py").write_text("y=1\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.py").write_text("z=1\n")

    files = {p.relative_to(tmp_path).as_posix() for p in iter_source_files(tmp_path, 2, DEFAULT_SKIP_DIRS)}
    assert "a.py" in files and "b.go" in files
    assert "c.txt" not in files
    assert "d1/d2/d3/deep.py" not in files
    assert "node_modules/x.py" not in files
