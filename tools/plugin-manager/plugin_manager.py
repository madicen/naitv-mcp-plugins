#!/usr/bin/env python3
"""plugin-manager: list / validate / test plugin manifests (JSON stdin/stdout)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 1_000_000
MAX_PLUGINS = 500
VALID_KINDS = frozenset({"rule", "workflow", "fact", "note", "tool", "project"})
VALID_DELIVERY = frozenset({"init", "on-demand", "review", ""})


def _error(message: str, *, code: int = 1) -> None:
    print(message, file=sys.stderr)
    sys.exit(code)


def validate_root_path(root: str) -> Path:
    raw = Path(root)
    if ".." in raw.parts:
        _error(f"root_path must not contain '..': {root}")
    path = raw.expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()
    if not path.exists():
        _error(f"root_path does not exist: {root}")
    if not path.is_dir():
        _error(f"root_path is not a directory: {root}")
    return path


def discover_manifests(root: Path) -> list[Path]:
    """Find plugin.json files under root. Prefer plugins/*/plugin.json."""
    nested = sorted(root.glob("plugins/*/plugin.json"))
    if nested:
        return nested[:MAX_PLUGINS]
    flat = sorted(p for p in root.glob("*/plugin.json") if p.is_file())
    return flat[:MAX_PLUGINS]


def rel_or_abs(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def load_manifest(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def resolve_plugin_path(root: Path, plugin: str) -> Path | None:
    candidates = [
        root / "plugins" / plugin / "plugin.json",
        root / plugin / "plugin.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def summarize(path: Path, root: Path, data: dict[str, Any]) -> dict[str, Any]:
    entries = data.get("entries") or []
    tool_count = sum(1 for e in entries if isinstance(e, dict) and e.get("kind") == "tool")
    return {
        "name": str(data.get("name") or path.parent.name),
        "version": str(data.get("version") or ""),
        "path": rel_or_abs(path, root),
        "entry_count": len(entries) if isinstance(entries, list) else 0,
        "tool_count": tool_count,
    }


def list_plugins(root: Path) -> dict[str, Any]:
    plugins: list[dict[str, Any]] = []
    for path in discover_manifests(root):
        data = load_manifest(path)
        if data is None:
            continue
        plugins.append(summarize(path, root, data))
    plugins.sort(key=lambda p: p["name"])
    return {"plugins": plugins, "count": len(plugins)}


def lint_manifest(name: str, data: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if data.get("name") and data["name"] != name:
        errors.append(f"name mismatch: manifest={data['name']!r} dir={name!r}")
    entries = data.get("entries") or []
    if not entries:
        errors.append("no entries")
    if not isinstance(entries, list):
        errors.append("entries must be an array")
        return errors, warnings
    seen: set[str] = set()
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entries[{i}]: not an object")
            continue
        kind = entry.get("kind", "")
        ename = entry.get("name", "")
        label = f"entries[{i}]/{ename or '?'}"
        if kind not in VALID_KINDS:
            errors.append(f"{label}: bad kind {kind!r}")
        if not ename:
            errors.append(f"{label}: missing name")
        elif ename in seen:
            errors.append(f"duplicate entry name {ename!r}")
        else:
            seen.add(ename)
        delivery = entry.get("delivery") or ""
        if delivery and delivery not in VALID_DELIVERY:
            errors.append(f"{label}: bad delivery {delivery!r}")
        if kind == "tool":
            fields = entry.get("fields") or {}
            if not isinstance(fields, dict) or not fields.get("exec"):
                errors.append(f"{label}: tool missing fields.exec")
            io_mode = (fields.get("io_mode") if isinstance(fields, dict) else None) or "text"
            if io_mode not in ("json", "JSON", "text", "TEXT"):
                errors.append(f"{label}: bad io_mode {io_mode!r}")
        body = entry.get("body")
        if body is None or (isinstance(body, str) and not body.strip()):
            errors.append(f"{label}: empty body")
    return errors, warnings


def validate_plugin(root: Path, plugin: str) -> dict[str, Any]:
    path = resolve_plugin_path(root, plugin)
    if path is None:
        return {
            "ok": False,
            "plugin": plugin,
            "path": "",
            "errors": [f"plugin not found: {plugin}"],
            "warnings": [],
        }
    data = load_manifest(path)
    if data is None:
        return {
            "ok": False,
            "plugin": plugin,
            "path": rel_or_abs(path, root),
            "errors": ["manifest is not valid JSON object"],
            "warnings": [],
        }
    errors, warnings = lint_manifest(plugin, data)
    return {
        "ok": not errors,
        "plugin": plugin,
        "path": rel_or_abs(path, root),
        "errors": errors,
        "warnings": warnings,
    }


def run_l2(root: Path, plugin: str) -> tuple[bool, list[str], str]:
    runner = root / "testing" / "contract" / "run_contract.py"
    if not runner.is_file():
        return False, ["root_path has no testing/contract/run_contract.py"], ""
    try:
        proc = subprocess.run(
            [sys.executable, str(runner), "--use-repo-tools", plugin],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=110,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, ["l2 timed out"], ""
    except OSError as exc:
        return False, [f"l2 failed to start: {exc}"], ""
    out = (proc.stdout or "") + (proc.stderr or "")
    # Truncate for stdout budget.
    if len(out) > 200_000:
        out = out[:200_000] + "\n…truncated…"
    ok = proc.returncode == 0
    errors = [] if ok else [f"l2 exited {proc.returncode}"]
    return ok, errors, out


def test_plugin(root: Path, plugin: str, layers: str) -> dict[str, Any]:
    layers = (layers or "lint").strip().lower()
    if layers not in ("lint", "l2"):
        _error("layers must be 'lint' or 'l2'")
    if layers == "lint":
        result = validate_plugin(root, plugin)
        return {
            "ok": result["ok"],
            "plugin": plugin,
            "layers": "lint",
            "errors": result["errors"],
            "output": "",
        }
    # Ensure plugin exists before shelling out.
    if resolve_plugin_path(root, plugin) is None:
        return {
            "ok": False,
            "plugin": plugin,
            "layers": "l2",
            "errors": [f"plugin not found: {plugin}"],
            "output": "",
        }
    ok, errors, output = run_l2(root, plugin)
    return {
        "ok": ok,
        "plugin": plugin,
        "layers": "l2",
        "errors": errors,
        "output": output,
    }


def main() -> None:
    tool = os.environ.get("TOOL_NAME", "").strip()
    if tool not in ("list_plugins", "validate_plugin", "test_plugin"):
        _error(f"unknown or missing TOOL_NAME: {tool!r}")

    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        _error(f"input exceeds {MAX_INPUT_BYTES} bytes")
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        _error(f"invalid JSON: {exc}")
    if not isinstance(data, dict):
        _error("input must be a JSON object")

    root_raw = data.get("root_path")
    if not root_raw:
        _error("root_path required")
    if not isinstance(root_raw, str):
        _error("root_path must be a string")
    root = validate_root_path(root_raw)

    if tool == "list_plugins":
        result = list_plugins(root)
    else:
        plugin = data.get("plugin")
        if not isinstance(plugin, str) or not plugin.strip():
            _error("plugin required")
        plugin = plugin.strip()
        if tool == "validate_plugin":
            result = validate_plugin(root, plugin)
        else:
            layers = data.get("layers", "lint")
            if layers is not None and not isinstance(layers, str):
                _error("layers must be a string")
            result = test_plugin(root, plugin, layers or "lint")

    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
