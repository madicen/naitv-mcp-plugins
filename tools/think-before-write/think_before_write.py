#!/usr/bin/env python3
"""think-before-write: checklist grounded in real paths/identifiers."""
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
    "plan_checklist",
    "check_assumptions",
    "render_pre_write_prompt",
}


def _error(message: str, *, code: int = 1) -> None:
    print(message, file=sys.stderr)
    sys.exit(code)


def validate_root_path(root: str) -> Path:
    return su.validate_root_path(root, error=_error)


def iter_files(root: Path, depth: int = 3) -> list[Path]:
    return su.iter_files(root, depth)


def _inventory(root: Path, files: list[Path], query: str, limit: int) -> tuple[list[str], list[str]]:
    paths: list[str] = []
    names: list[str] = []
    for f in files:
        r = su.rel(f, root)
        text = su.read_text(f)
        idents = su.extract_identifiers(text, f.suffix)
        if query and not su.match_query(query, r, text, idents):
            continue
        paths.append(r)
        names.extend(idents)
        if len(paths) >= limit:
            break
    names = list(dict.fromkeys(names))[:limit]
    return paths, names


def handle(tool: str, root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    query = str(data.get("query") or data.get("pattern") or data.get("text") or "").strip()
    path_s = str(data.get("path") or data.get("file") or "README.md").strip()
    limit = max(1, min(int(data.get("limit", 20)), 100))
    files = su.iter_files(root, depth)
    paths, names = _inventory(root, files, query, limit)

    if tool in ("plan_checklist", "render_pre_write_prompt"):
        lines = [
            f"# {tool}",
            f"# root={root.name}",
            f"# query={query or path_s}",
        ]
        if paths:
            lines.append("# paths=" + ",".join(paths[:10]))
        if names:
            lines.append("# names=" + ",".join(names[:10]))
        lines.append("- [ ] confirm target paths exist")
        if names:
            lines.append(f"- [ ] touch only: {', '.join(names[:5])}")
        body = "\n".join(lines) + "\n"
        return {
            "generated": body,
            "ok": True,
            "items": [{"text": body, "paths": paths, "names": names}],
            "tool": tool,
        }

    if tool == "check_assumptions":
        violations: list[dict[str, Any]] = []
        if query and not paths:
            violations.append(
                {
                    "path": path_s,
                    "rule": "no_match",
                    "message": f"no files/identifiers matched {query!r}",
                }
            )
        target = root / path_s
        if path_s and not target.exists():
            violations.append(
                {"path": path_s, "rule": "missing_path", "message": "path does not exist"}
            )
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
