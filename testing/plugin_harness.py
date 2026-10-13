#!/usr/bin/env python3
"""Plugin discovery + harness.json for shared L1–L5 runners.

Shared runners must not hardcode plugin names. Read plugin.json / harness.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGINS_DIR = REPO_ROOT / "plugins"

DEFAULT_LAYERS = {
    "l1": True,
    "l2": True,
    "l3_golden": True,
    "l4": True,
    "l5": False,
}


def plugin_dir(name: str) -> Path:
    return PLUGINS_DIR / name


def manifest_path(name: str) -> Path:
    """Canonical test layout: plugins/<name>/plugin.json."""
    return plugin_dir(name) / "plugin.json"


def load_manifest(name: str) -> dict[str, Any]:
    path = manifest_path(name)
    if not path.is_file():
        raise FileNotFoundError(f"missing plugin manifest: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def tool_names(manifest: dict[str, Any]) -> list[str]:
    return [
        e["name"]
        for e in manifest.get("entries", [])
        if e.get("kind") == "tool" and e.get("name")
    ]


def has_json_tools(manifest: dict[str, Any]) -> bool:
    for e in manifest.get("entries", []):
        if e.get("kind") != "tool":
            continue
        fields = e.get("fields") or {}
        if fields.get("exec"):
            return True
    return False


def infer_profile(manifest: dict[str, Any]) -> str:
    tools = has_json_tools(manifest)
    rules = any(e.get("kind") in ("rule", "workflow", "fact", "note") for e in manifest.get("entries", []))
    if tools and rules:
        return "mixed"
    if tools:
        return "json_tools"
    return "rules_only"


def load_harness(name: str) -> dict[str, Any]:
    """Load optional harness.json; fill defaults from manifest."""
    manifest = load_manifest(name)
    path = plugin_dir(name) / "harness.json"
    raw: dict[str, Any] = {}
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))

    profile = raw.get("profile") or infer_profile(manifest)
    layers = {**DEFAULT_LAYERS, **(raw.get("layers") or {})}
    if profile == "rules_only":
        layers["l2"] = False
        layers["l3_golden"] = False
        layers["l4"] = False
        layers["l5"] = False

    return {
        "name": name,
        "profile": profile,
        "layers": layers,
        "coverage": raw.get("coverage") or {},
        "perf": raw.get("perf") or {},
        "l4": raw.get("l4") or {},
        "l5": raw.get("l5") or {},
        "golden": raw.get("golden") or {},
        "tool_names": tool_names(manifest),
        "manifest": manifest,
    }


def resolve_impl_paths(name: str, harness: dict[str, Any]) -> list[Path]:
    cov = harness.get("coverage") or {}
    search = cov.get("search_paths") or [
        f"tools/{name}",
        f"plugins/{name}",
    ]
    out: list[Path] = []
    for rel in search:
        p = REPO_ROOT / rel
        if p.is_dir():
            out.append(p)
    return out


def coverage_module(name: str, harness: dict[str, Any]) -> str | None:
    cov = harness.get("coverage") or {}
    # Empty coverage {} means disabled (scaffold default).
    if not cov:
        return None
    if "module" in cov:
        return str(cov["module"]) if cov["module"] else None
    # Infer: first *.py that isn't test under tools/ or plugins/
    for base in resolve_impl_paths(name, harness):
        for py in sorted(base.glob("*.py")):
            if py.name.startswith("test"):
                continue
            return py.stem
    return None


def list_testable_plugins() -> list[str]:
    names: list[str] = []
    for path in sorted(PLUGINS_DIR.glob("*/plugin.json")):
        names.append(path.parent.name)
    return names


def _sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def dump_shell(name: str) -> str:
    h = load_harness(name)
    layers = h["layers"]
    cov_mod = coverage_module(name, h) or ""
    paths = resolve_impl_paths(name, h)
    cov_path = str(paths[0]) if paths else ""
    fail_under = (h.get("coverage") or {}).get("fail_under", 80)
    tools = " ".join(h["tool_names"])
    l5_plugins = " ".join((h.get("l5") or {}).get("treatment_plugins") or [name])
    lines = [
        f"PROFILE={_sh_quote(str(h['profile']))}",
        f"LAYER_L1={_sh_quote('1' if layers.get('l1') else '0')}",
        f"LAYER_L2={_sh_quote('1' if layers.get('l2') else '0')}",
        f"LAYER_L3_GOLDEN={_sh_quote('1' if layers.get('l3_golden') else '0')}",
        f"LAYER_L4={_sh_quote('1' if layers.get('l4') else '0')}",
        f"LAYER_L5={_sh_quote('1' if layers.get('l5') else '0')}",
        f"COV_MODULE={_sh_quote(cov_mod)}",
        f"COV_PATH={_sh_quote(cov_path)}",
        f"COV_FAIL_UNDER={_sh_quote(str(fail_under))}",
        f"TOOL_NAMES={_sh_quote(tools)}",
        f"L5_TREATMENT_PLUGINS={_sh_quote(l5_plugins)}",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_dump = sub.add_parser("dump", help="shell KEY=value for scripts/test.sh")
    p_dump.add_argument("plugin")

    p_list = sub.add_parser("list", help="list plugins with plugin.json")
    p_json = sub.add_parser("json", help="print resolved harness as JSON")
    p_json.add_argument("plugin")

    args = parser.parse_args()
    if args.cmd == "dump":
        sys.stdout.write(dump_shell(args.plugin))
        return 0
    if args.cmd == "list":
        for n in list_testable_plugins():
            print(n)
        return 0
    if args.cmd == "json":
        h = load_harness(args.plugin)
        # Drop full manifest from shell-facing dump size
        out = {k: v for k, v in h.items() if k != "manifest"}
        json.dump(out, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
