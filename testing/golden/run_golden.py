#!/usr/bin/env python3
"""L3 golden output tests for a plugin (stable fields only)."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "testing" / "fixtures"
GOLDEN_DIR = Path(__file__).resolve().parent
MASK_KEYS = frozenset({"cached", "commit"})

# Fixtures exercised per structural-anchor tool
DEFAULT_FIXTURES = ("py-small", "go-small", "empty", "mixed-polyglot", "hostile")


def load_plugin(plugin_name: str) -> dict[str, Any]:
    path = REPO_ROOT / "plugins" / plugin_name / "plugin.json"
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_home(plugin_name: str, home: Path) -> None:
    src = REPO_ROOT / "tools" / plugin_name
    if not src.is_dir():
        raise SystemExit(f"missing tools/{plugin_name}")
    dest_parent = home / ".config" / "naitv-mcp" / "tools"
    dest_parent.mkdir(parents=True, exist_ok=True)
    dest = dest_parent / plugin_name
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    dest.symlink_to(src, target_is_directory=True)


def expand_exec(exec_str: str, home: Path) -> str:
    return os.path.expanduser(exec_str.replace("~", str(home)))


def mask(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if key in MASK_KEYS:
                continue
            out[key] = mask(value)
        return out
    if isinstance(obj, list):
        return [mask(v) for v in obj]
    return obj


def sort_payload(tool: str, obj: dict[str, Any]) -> dict[str, Any]:
    """Stable ordering: packages by path, symbols by (line, name)."""
    data = json.loads(json.dumps(obj))  # deep copy via JSON
    if tool == "get_project_map" and isinstance(data.get("packages"), list):
        for pkg in data["packages"]:
            pkg["symbols"] = sorted(
                pkg.get("symbols", []),
                key=lambda s: (s.get("line", 0), s.get("name", "")),
            )
        data["packages"] = sorted(
            data["packages"], key=lambda p: (p.get("path", ""), p.get("name", ""))
        )
        if isinstance(data.get("languages"), list):
            data["languages"] = sorted(data["languages"])
    if tool == "list_languages" and isinstance(data.get("languages"), list):
        data["languages"] = sorted(
            data["languages"], key=lambda row: row.get("id", "")
        )
    return data


def run_tool(exec_str: str, root: Path, home: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["XDG_CACHE_HOME"] = str(home / ".cache")
    payload = json.dumps({"root_path": str(root), "depth": 3}) + "\n"
    proc = subprocess.run(
        ["sh", "-c", expand_exec(exec_str, home)],
        input=payload.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"tool failed ({proc.returncode}): {proc.stderr.decode()[:500]}"
        )
    return json.loads(proc.stdout.decode("utf-8"))


def golden_path(plugin: str, tool: str, fixture: str) -> Path:
    return GOLDEN_DIR / plugin / tool / f"{fixture}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plugin")
    parser.add_argument(
        "--update-golden",
        action="store_true",
        help="rewrite golden files from current tool output",
    )
    parser.add_argument(
        "--fixtures",
        default=",".join(DEFAULT_FIXTURES),
        help="comma-separated fixture names under testing/fixtures/",
    )
    args = parser.parse_args()
    fixtures = [f.strip() for f in args.fixtures.split(",") if f.strip()]
    plugin = load_plugin(args.plugin)
    tools = [e for e in plugin.get("entries", []) if e.get("kind") == "tool"]
    failures = 0
    updated = 0

    with tempfile.TemporaryDirectory(prefix="naitv-golden-") as tmp:
        home = Path(tmp)
        prepare_home(args.plugin, home)
        for entry in tools:
            name = entry["name"]
            exec_str = (entry.get("fields") or {}).get("exec")
            if not exec_str:
                print(f"FAIL {name}: missing exec")
                failures += 1
                continue
            for fixture in fixtures:
                root = FIXTURES_DIR / fixture
                if not root.is_dir():
                    print(f"FAIL {name}/{fixture}: missing fixture dir")
                    failures += 1
                    continue
                try:
                    actual = mask(sort_payload(name, run_tool(exec_str, root, home)))
                except Exception as exc:
                    print(f"FAIL {name}/{fixture}: {exc}")
                    failures += 1
                    continue
                path = golden_path(args.plugin, name, fixture)
                if args.update_golden or not path.is_file():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(
                        json.dumps(actual, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    updated += 1
                    print(f"UPDATE {name}/{fixture}")
                    continue
                expected = json.loads(path.read_text(encoding="utf-8"))
                if actual != expected:
                    print(f"FAIL {name}/{fixture}: golden mismatch")
                    failures += 1
                else:
                    print(f"PASS {name}/{fixture}")

    print(f"\nSummary: failures={failures} updated={updated}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
