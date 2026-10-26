"""L1: cache-manager tools."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "tools" / "cache-manager"
sys.path.insert(0, str(TOOLS))
import cache_manager as cm  # noqa: E402


class _FakeStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)


@pytest.fixture()
def cache_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / ".cache"))
    return tmp_path


def test_put_get_roundtrip(cache_home: Path) -> None:
    put = cm.cache_put("k1", {"a": 1}, namespace="t", ttl=60)
    assert put["stored"] is True
    got = cm.cache_get("k1", namespace="t")
    assert got["hit"] is True
    assert got["value"] == {"a": 1}


def test_get_miss(cache_home: Path) -> None:
    got = cm.cache_get("nope", namespace="t")
    assert got["hit"] is False
    assert got["value"] is None


def test_stats_and_hit_rate(cache_home: Path) -> None:
    cm.cache_get("x", namespace="s")
    cm.cache_put("x", "v", namespace="s", ttl=0)
    cm.cache_get("x", namespace="s")
    st = cm.cache_stats(namespace="s")
    assert st["entries"] == 1
    assert st["bytes"] > 0
    assert st["misses"] == 1
    assert st["hits"] == 1
    assert st["hit_rate"] == 0.5


def test_prune_clear(cache_home: Path) -> None:
    cm.cache_put("a", "1", namespace="p", ttl=0)
    cm.cache_put("b", "2", namespace="p", ttl=0)
    out = cm.cache_prune(namespace="p", max_bytes=0)
    assert out["removed"] >= 2
    assert out["remaining"] == 0


def test_prune_lru(cache_home: Path) -> None:
    cm.cache_put("old", "x" * 50, namespace="lru", ttl=0)
    cm.cache_put("new", "y" * 50, namespace="lru", ttl=0)
    cm.cache_get("new", namespace="lru")  # touch new
    out = cm.cache_prune(namespace="lru", max_bytes=60)
    assert out["remaining"] == 1
    assert cm.cache_get("new", namespace="lru")["hit"] is True


def test_ttl_expiry(cache_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    t0 = 1_700_000_000.0
    monkeypatch.setattr(cm.time, "time", lambda: t0)
    cm.cache_put("e2", "v", namespace="ttl2", ttl=10)
    monkeypatch.setattr(cm.time, "time", lambda: t0 + 20)
    assert cm.cache_get("e2", namespace="ttl2")["hit"] is False


def test_bad_key(cache_home: Path) -> None:
    with pytest.raises(SystemExit):
        cm.validate_key("../x")


def test_bad_namespace(cache_home: Path) -> None:
    with pytest.raises(SystemExit):
        cm.validate_namespace("bad ns")


def test_value_too_large(cache_home: Path) -> None:
    with pytest.raises(SystemExit):
        cm.cache_put("k", "x" * (cm.MAX_VALUE_BYTES + 1), namespace="big")


def test_main_get(cache_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "cache_get")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b'{"key":"z","namespace":"m"}\n'))
    cm.main()
    out = json.loads(capsys.readouterr().out)
    assert out["hit"] is False


def test_main_put(cache_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "cache_put")
    payload = {"key": "z", "value": 1, "namespace": "m", "ttl": 10}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\n").encode()))
    cm.main()
    out = json.loads(capsys.readouterr().out)
    assert out["stored"] is True


def test_main_stats(cache_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "cache_stats")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b'{"namespace":"m"}\n'))
    cm.main()
    out = json.loads(capsys.readouterr().out)
    assert "entries" in out


def test_main_prune(cache_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", "cache_prune")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b'{"namespace":"m","max_bytes":0}\n'))
    cm.main()
    out = json.loads(capsys.readouterr().out)
    assert out["remaining"] == 0


def test_main_missing_key(monkeypatch: pytest.MonkeyPatch, cache_home: Path) -> None:
    monkeypatch.setenv("TOOL_NAME", "cache_get")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        cm.main()


def test_main_bad_json(monkeypatch: pytest.MonkeyPatch, cache_home: Path) -> None:
    monkeypatch.setenv("TOOL_NAME", "cache_get")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{bad\n"))
    with pytest.raises(SystemExit):
        cm.main()


def test_main_unknown(monkeypatch: pytest.MonkeyPatch, cache_home: Path) -> None:
    monkeypatch.setenv("TOOL_NAME", "nope")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{}\n"))
    with pytest.raises(SystemExit):
        cm.main()


def test_main_missing_value(monkeypatch: pytest.MonkeyPatch, cache_home: Path) -> None:
    monkeypatch.setenv("TOOL_NAME", "cache_put")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b'{"key":"k"}\n'))
    with pytest.raises(SystemExit):
        cm.main()


def test_main_too_large(monkeypatch: pytest.MonkeyPatch, cache_home: Path) -> None:
    monkeypatch.setenv("TOOL_NAME", "cache_get")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{" + b"a" * (cm.MAX_INPUT_BYTES + 5)))
    with pytest.raises(SystemExit):
        cm.main()
