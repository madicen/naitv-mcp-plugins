import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures"

sys.path.insert(0, str(ROOT))
import symbol_navigator


def run_cli(
    tool: str,
    home: Path,
    payload: dict,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["TOOL_NAME"] = tool
    return subprocess.run(
        [sys.executable, str(ROOT / "symbol_navigator.py")],
        input=json.dumps(payload) + "\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def test_this_repo_find_and_cache(tmp_path: Path):
    home = tmp_path / "home"
    payload = {
        "root_path": str(REPO / "tools" / "symbol-navigator"),
        "depth": 3,
        "symbol": "ensure_index",
    }
    first = run_cli("find_symbol_definition", home, payload)
    second = run_cli("find_symbol_definition", home, payload)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    out1 = json.loads(first.stdout)
    out2 = json.loads(second.stdout)
    assert out1["cached"] is False
    assert out2.get("cached") is True or out2.get("file")
    assert out1["source"] == "ast"
    assert out1["file"].endswith("symbol_navigator.py")
    assert "ensure_index" in out1["signature"]


def test_warm_lookup_under_100ms(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = FIXTURES
    depth = 2
    skip = symbol_navigator.normalize_skip_dirs(None)

    symbol_navigator.find_symbol_definition(root, depth, skip, "Greeter")

    t0 = time.perf_counter()
    result = symbol_navigator.find_symbol_definition(root, depth, skip, "Greeter")
    elapsed = time.perf_counter() - t0

    assert result.get("cached") is True
    assert result["type"] == "function"
    assert elapsed < 0.1
