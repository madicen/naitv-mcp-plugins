from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from structural_anchor import iter_source_files, DEFAULT_SKIP_DIRS


def test_iter_respects_depth_and_extensions(tmp_path: Path):
    (tmp_path / "a.py").write_text("x=1\n")
    (tmp_path / "b.go").write_text("package main\n")
    (tmp_path / "c.txt").write_text("nope\n")
    sub = tmp_path / "d1" / "d2" / "d3"
    sub.mkdir(parents=True)
    (sub / "deep.py").write_text("y=1\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.py").write_text("z=1\n")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "h.py").write_text("h=1\n")

    files = {p.relative_to(tmp_path).as_posix() for p in iter_source_files(tmp_path, depth=2, skip_dirs=DEFAULT_SKIP_DIRS)}
    assert "a.py" in files
    assert "b.go" in files
    assert "c.txt" not in files
    assert "d1/d2/d3/deep.py" not in files  # depth 2 hard stop (root=0)
    assert "node_modules/x.py" not in files
    assert ".hidden/h.py" not in files
