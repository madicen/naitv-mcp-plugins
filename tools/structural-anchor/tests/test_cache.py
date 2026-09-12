from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from structural_anchor import (
    cache_dir,
    cache_key,
    fingerprint,
    get_project_map,
    load_cache,
    save_cache,
)


def test_cache_roundtrip(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))
    key = cache_key(Path("/repo"), 3, {"vendor"}, "abc")
    assert load_cache(key) is None
    save_cache(key, {"packages": [], "languages": [], "statistics": {}})
    assert load_cache(key)["packages"] == []
    assert (cache_dir() / f"{key}.json").is_file()


def test_fingerprint_changes_and_cache_misses_when_git_worktree_becomes_dirty(
    monkeypatch, tmp_path: Path
):
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    source = root / "sample.py"
    source.write_text("value = 1\n")
    subprocess.run(["git", "add", "sample.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)

    clean = fingerprint(root)
    assert get_project_map(root, 3, set())["cached"] is False
    assert get_project_map(root, 3, set())["cached"] is True
    source.write_text("value = 2\n")

    assert fingerprint(root) != clean
    assert get_project_map(root, 3, set())["cached"] is False
    assert get_project_map(root, 3, set())["cached"] is False


def test_go_degraded_build_is_not_cached(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    (root / "sample.go").write_text("package sample\n\nfunc Hello() {}\n")
    monkeypatch.setattr("structural_anchor.ensure_go_symbols_bin", lambda _src: None)

    first = get_project_map(root, 3, set())
    second = get_project_map(root, 3, set())

    assert first["cached"] is False
    assert second["cached"] is False
    assert not list(cache_dir().glob("*.json"))
