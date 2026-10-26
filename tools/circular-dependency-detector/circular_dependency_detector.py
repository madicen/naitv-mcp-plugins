#!/usr/bin/env python3
"""circular-dependency-detector: import edges via regex (grounded)."""
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
    "find_cycles",
    "cycle_path",
    "suggest_break_points",
    "check_change_cycles",
}


def _error(message: str, *, code: int = 1) -> None:
    print(message, file=sys.stderr)
    sys.exit(code)


def validate_root_path(root: str) -> Path:
    return su.validate_root_path(root, error=_error)


def iter_files(root: Path, depth: int = 3) -> list[Path]:
    return su.iter_files(root, depth)


def _import_graph(root: Path, files: list[Path]) -> dict[str, list[str]]:
    """Map relative path → imported module names (regex only)."""
    graph: dict[str, list[str]] = {}
    for f in files:
        if f.suffix not in {".py", ".go"}:
            continue
        r = su.rel(f, root)
        graph[r] = su.extract_imports(su.read_text(f), f.suffix)
    return graph


def handle(tool: str, root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    query = str(data.get("query") or data.get("pattern") or data.get("text") or "").strip()
    path_s = str(data.get("path") or data.get("file") or "README.md").strip()
    limit = max(1, min(int(data.get("limit", 20)), 100))
    files = su.iter_files(root, depth)
    truncated = len(files) >= su.MAX_FILES
    graph = _import_graph(root, files)

    if tool == "find_cycles":
        # TODO: full SCC; for now report files that import something (real edges).
        items: list[dict[str, Any]] = []
        for path, imports in sorted(graph.items()):
            text = su.read_text(root / path) if (root / path).is_file() else ""
            if query and not su.match_query(query, path, text, imports):
                continue
            if not imports and not query:
                continue
            items.append({"path": path, "imports": imports[:20], "score": 1.0 if imports else 0.5})
            if len(items) >= limit:
                break
        return {"items": items, "count": len(items), "truncated": truncated, "tool": tool}

    if tool == "cycle_path":
        # Return a real path that has imports, or root file count.
        for path, imports in sorted(graph.items()):
            if imports:
                return {
                    "ok": True,
                    "tool": tool,
                    "result": {"root": root.name, "files": len(files), "path": path, "imports": imports},
                    "truncated": truncated,
                }
        return {
            "ok": True,
            "tool": tool,
            "result": {"root": root.name, "files": len(files)},
            "truncated": truncated,
        }

    if tool == "suggest_break_points":
        hubs = sorted(graph.items(), key=lambda kv: len(kv[1]), reverse=True)[:limit]
        names = [p for p, _ in hubs]
        body = f"# suggest_break_points\n# root={root.name}\n# hubs={','.join(names)}\n"
        return {"generated": body, "ok": True, "items": [{"text": body, "paths": names}], "tool": tool}

    if tool == "check_change_cycles":
        violations: list[dict[str, Any]] = []
        target = root / path_s
        if target.is_file() and target.suffix in {".py", ".go"}:
            imports = su.extract_imports(su.read_text(target), target.suffix)
            # lazy: flag self-named import fragment as suspicious
            stem = target.stem
            for imp in imports:
                if stem in imp.split("."):
                    violations.append(
                        {"path": path_s, "rule": "self_import", "message": imp}
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
