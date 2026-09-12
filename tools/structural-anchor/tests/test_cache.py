from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from structural_anchor import cache_key, load_cache, save_cache, cache_dir


def test_cache_roundtrip(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))
    key = cache_key(Path("/repo"), 3, {"vendor"}, "abc")
    assert load_cache(key) is None
    save_cache(key, {"packages": [], "languages": [], "statistics": {}})
    assert load_cache(key)["packages"] == []
    assert (cache_dir() / f"{key}.json").is_file()
