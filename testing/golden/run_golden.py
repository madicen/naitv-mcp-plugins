#!/usr/bin/env python3
"""L3 golden output tests for a plugin (stable fields only).

Per-tool query extras and fixtures come from plugins/<name>/harness.json → golden.
Absolute paths under the fixture root are rewritten to fixture-relative form.
"""
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
sys.path.insert(0, str(REPO_ROOT / "testing"))

from plugin_harness import load_harness, load_manifest  # noqa: E402

MASK_KEYS = frozenset({"cached", "commit"})
DEFAULT_FIXTURES = ("py-small", "go-small", "empty", "mixed-polyglot", "hostile")


def prepare_home(plugin_name: str, home: Path) -> None:
    src = REPO_ROOT / "tools" / plugin_name
    if not src.is_dir():
        src = REPO_ROOT / "plugins" / plugin_name
    if not src.is_dir():
        raise SystemExit(f"missing tools/{plugin_name} (and plugins/{plugin_name})")
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
        return {k: mask(v) for k, v in obj.items() if k not in MASK_KEYS}
    if isinstance(obj, list):
        return [mask(v) for v in obj]
    return obj


def relativize(obj: Any, root: Path) -> Any:
    """Rewrite absolute paths under fixture root to relative paths."""
    root_s = str(root.resolve())
    if isinstance(obj, str):
        if obj == root_s or obj.startswith(root_s + os.sep):
            rel = obj[len(root_s) :].lstrip("/\\")
            return rel or "."
        return obj
    if isinstance(obj, list):
        return [relativize(v, root) for v in obj]
    if isinstance(obj, dict):
        return {k: relativize(v, root) for k, v in obj.items()}
    return obj


def sort_payload(tool: str, obj: dict[str, Any]) -> dict[str, Any]:
    """Stable ordering for golden comparison."""
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
    if tool == "search_by_pattern" and isinstance(data.get("results"), list):
        data["results"] = sorted(
            data["results"],
            key=lambda r: (r.get("file", ""), r.get("line", 0), r.get("name", "")),
        )
    if tool == "find_symbol_definition" and isinstance(data.get("matches"), list):
        data["matches"] = sorted(
            data["matches"],
            key=lambda m: (m.get("file", ""), m.get("line", 0), m.get("type", "")),
        )
    if tool == "get_symbol_references" and isinstance(data.get("references"), list):
        data["references"] = sorted(
            data["references"],
            key=lambda r: (r.get("file", ""), r.get("line", 0), r.get("column", 0)),
        )
    return data


def run_tool(
    exec_str: str,
    root: Path,
    home: Path,
    query: dict[str, Any],
) -> dict[str, Any]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["XDG_CACHE_HOME"] = str(home / ".cache")
    payload = {"depth": 3, **query, "root_path": str(root.resolve())}
    proc = subprocess.run(
        ["sh", "-c", expand_exec(exec_str, home)],
        input=(json.dumps(payload) + "\n").encode("utf-8"),
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
        default="",
        help="comma-separated fixture names (default: harness.golden.fixtures or builtin)",
    )
    args = parser.parse_args()

    harness = load_harness(args.plugin)
    golden_cfg = harness.get("golden") or {}
    if args.fixtures:
        fixtures = [f.strip() for f in args.fixtures.split(",") if f.strip()]
    else:
        fixtures = list(golden_cfg.get("fixtures") or DEFAULT_FIXTURES)

    queries: dict[str, dict[str, Any]] = golden_cfg.get("queries") or {}
    manifest = load_manifest(args.plugin)
    tools = [e for e in manifest.get("entries", []) if e.get("kind") == "tool"]
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
            query = dict(queries.get(name) or {})
            for fixture in fixtures:
                root = FIXTURES_DIR / fixture
                if not root.is_dir():
                    print(f"FAIL {name}/{fixture}: missing fixture dir")
                    failures += 1
                    continue
                try:
                    raw = run_tool(exec_str, root, home, query)
                    actual = mask(sort_payload(name, relativize(raw, root)))
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
