import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import symbol_navigator
from symbol_navigator import (
    build_index,
    cache_key,
    ensure_go_nav_bin,
    load_index,
    save_index,
)


def test_cache_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    key = cache_key(Path("/repo"), 3, {"vendor"}, "abc")
    assert load_index(key) is None
    save_index(key, {"defs": [{"name": "X"}]})
    assert load_index(key)["defs"][0]["name"] == "X"


def test_go_degraded_not_saved(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "p"
    root.mkdir()
    (root / "a.go").write_text("package a\n")
    monkeypatch.setattr("symbol_navigator.ensure_go_nav_bin", lambda _s: None)
    payload, degraded = build_index(root, 3, set())
    assert payload == {"defs": []}
    assert degraded is True


def test_build_index_merges_python_and_go(monkeypatch, tmp_path):
    (tmp_path / "a.py").write_text("def python_def():\n    pass\n")
    go_file = tmp_path / "a.go"
    go_file.write_text("package a\nfunc GoDef() {}\n")
    monkeypatch.setattr("symbol_navigator.ensure_go_nav_bin", lambda _s: Path("/go-nav"))

    def run(cmd, **kwargs):
        assert cmd == ["/go-nav"]
        request = json.loads(kwargs["input"])
        assert request == {"mode": "index", "files": [str(go_file)]}
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps({"defs": [{"name": "GoDef"}], "errors": 0}),
            stderr="",
        )

    monkeypatch.setattr("symbol_navigator.subprocess.run", run)
    payload, degraded = build_index(tmp_path, 3, set())
    assert {definition["name"] for definition in payload["defs"]} == {
        "python_def",
        "GoDef",
    }
    assert degraded is False


def test_ensure_go_nav_bin_wraps_oserror(monkeypatch, tmp_path):
    src_dir = tmp_path / "go_nav"
    src_dir.mkdir()
    (src_dir / "main.go").write_text("package main\n")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    def fail(*_args, **_kwargs):
        raise OSError("go unavailable")

    monkeypatch.setattr("symbol_navigator.subprocess.run", fail)
    assert ensure_go_nav_bin(src_dir) is None


def test_ensure_go_nav_bin_reuses_newer_binary(monkeypatch, tmp_path):
    src_dir = tmp_path / "go_nav"
    src_dir.mkdir()
    main_go = src_dir / "main.go"
    main_go.write_text("package main\n")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    output = symbol_navigator.bin_dir() / "go-nav"
    output.parent.mkdir(parents=True)
    output.write_text("binary")
    output.touch()
    main_go.touch()
    output.touch()

    monkeypatch.setattr(
        "symbol_navigator.subprocess.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected build")),
    )
    assert ensure_go_nav_bin(src_dir) == output
