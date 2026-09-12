import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_get_project_map_cli(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text("def f():\n    return 1\n")
    env = os.environ.copy()
    env["TOOL_NAME"] = "get_project_map"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "structural_anchor.py")],
        input=json.dumps({"root_path": str(tmp_path), "depth": 5}) + "\n",
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert "packages" in out and "statistics" in out
    assert out.get("cached") is False
