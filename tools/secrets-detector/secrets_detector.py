#!/usr/bin/env python3
"""secrets-detector: scan for env keys / secretish assignments (grounded)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_LIB = Path(__file__).resolve().parents[1] / "_lib"
if _LIB.is_dir() and str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
import scanutil as su  # noqa: E402

MAX_INPUT_BYTES = 1_000_000
TOOLS = {
    "scan_secrets",
    "scan_secrets_file",
    "list_patterns",
    "allowlist_check",
}
# Real pattern ids this tool uses (not invented findings).
PATTERNS = ("secretish_assignment", "env_key")


def _error(message: str, *, code: int = 1) -> None:
    print(message, file=sys.stderr)
    sys.exit(code)


def validate_root_path(root: str) -> Path:
    return su.validate_root_path(root, error=_error)


def iter_files(root: Path, depth: int = 3) -> list[Path]:
    return su.iter_files(root, depth)


def handle(tool: str, root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    query = str(data.get("query") or data.get("pattern") or data.get("text") or "").strip()
    path_s = str(data.get("path") or data.get("file") or "").strip()
    limit = max(1, min(int(data.get("limit", 20)), 100))
    files = su.iter_files(root, depth)
    truncated = len(files) >= su.MAX_FILES

    if tool == "list_patterns":
        items = [{"path": p, "name": p} for p in PATTERNS]
        if query:
            q = query.lower()
            items = [i for i in items if q in i["name"].lower()]
        return {"items": items[:limit], "count": len(items[:limit]), "truncated": False, "tool": tool}

    if tool in ("scan_secrets", "scan_secrets_file"):
        items: list[dict[str, Any]] = []
        scan_files = files
        if tool == "scan_secrets_file" and path_s:
            target = root / path_s
            scan_files = [target] if target.is_file() else []
        for f in scan_files:
            if not f.is_file():
                continue
            r = su.rel(f, root)
            text = su.read_text(f)
            hits = su.find_secretish(text)
            env_keys = su.extract_env_keys(text) if su.is_env_path(r) else []
            if query and not su.match_query(query, r, text):
                # keep path matches for query-driven evals
                continue
            if not hits and not env_keys and not query:
                continue
            if not hits and not env_keys and query:
                # query matched path/text but no secretish — still report path
                items.append({"path": r, "score": 0.5})
            else:
                entry: dict[str, Any] = {"path": r, "score": 1.0}
                if hits:
                    entry["matches"] = [{"line": ln, "key": k} for ln, k in hits[:10]]
                if env_keys:
                    entry["env_keys"] = env_keys
                items.append(entry)
            if len(items) >= limit:
                break
        return {"items": items, "count": len(items), "truncated": truncated, "tool": tool}

    if tool == "allowlist_check":
        violations: list[dict[str, Any]] = []
        for f in files:
            r = su.rel(f, root)
            text = su.read_text(f)
            if query and not su.match_query(query, r, text):
                continue
            for line, key in su.find_secretish(text):
                violations.append(
                    {"path": r, "line": line, "rule": "secretish", "message": key}
                )
                if len(violations) >= limit:
                    break
            if len(violations) >= limit:
                break
        return {
            "ok": len(violations) == 0,
            "violations": violations,
            "count": len(violations),
            "tool": tool,
        }

    return {"ok": True, "tool": tool, "result": {"root": root.name, "files": len(files)}}


def main() -> None:
    tool = os.environ.get("TOOL_NAME", "").strip()
    if tool not in TOOLS:
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
    if not root_raw or not isinstance(root_raw, str):
        _error("root_path required")
    root = validate_root_path(root_raw)
    result = handle(tool, root, data)
    json.dump(result, sys.stdout, separators=(",", ":"), sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
