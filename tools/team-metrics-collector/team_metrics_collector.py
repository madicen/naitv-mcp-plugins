#!/usr/bin/env python3
"""team-metrics-collector: generated JSON I/O tools (stdlib, deterministic, bounded)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 1_000_000
MAX_FILES = 500
MAX_FILE_BYTES = 64_000
SKIP = {".git", "node_modules", "vendor", ".venv", "__pycache__", "dist", "build"}
TOOLS = {
        'collect_commit_metrics',
        'collect_review_metrics',
        'aggregate_metrics',
        'export_metrics'
}


def _error(message: str, *, code: int = 1) -> None:
    print(message, file=sys.stderr)
    sys.exit(code)


def validate_root_path(root: str) -> Path:
    raw = Path(root)
    if ".." in raw.parts:
        _error(f"root_path must not contain '..': {root}")
    path = raw.expanduser()
    path = path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
    if not path.exists():
        _error(f"root_path does not exist: {root}")
    if not path.is_dir():
        _error(f"root_path is not a directory: {root}")
    return path


def iter_files(root: Path, depth: int = 3) -> list[Path]:
    out: list[Path] = []

    def walk(d: Path, cur: int) -> None:
        if len(out) >= MAX_FILES:
            return
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name)
        except OSError:
            return
        for ent in entries:
            if len(out) >= MAX_FILES:
                return
            name = ent.name
            if ent.is_dir(follow_symlinks=False):
                if name in SKIP or name.startswith("."):
                    continue
                if cur + 1 > depth:
                    continue
                walk(Path(ent.path), cur + 1)
            elif ent.is_file(follow_symlinks=False):
                out.append(Path(ent.path))

    walk(root, 0)
    return out


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return path.name


def read_text(path: Path) -> str:
    try:
        data = path.read_bytes()[:MAX_FILE_BYTES]
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")


def handle(tool: str, root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    query = str(data.get("query") or data.get("pattern") or data.get("text") or "").strip()
    path_s = str(data.get("path") or data.get("file") or "README.md").strip()
    limit = max(1, min(int(data.get("limit", 20)), 100))
    files = iter_files(root, depth)
    truncated = len(files) >= MAX_FILES

    if tool.startswith(("list_", "find_", "scan_", "search_", "mine_", "extract_")) or tool.endswith(
        ("_summary", "_report", "_stats")
    ):
        items = []
        q = query.lower()
        for f in files:
            r = rel(f, root)
            text = read_text(f)
            if q and q not in text.lower() and q not in r.lower():
                continue
            items.append({"path": r, "score": 1.0 if not q else round(min(1.0, len(q) / max(len(r), 1)), 4)})
            if len(items) >= limit:
                break
        if not items and not q:
            items = [{"path": rel(f, root), "score": 0.0} for f in files[:limit]]
        return {"items": items, "count": len(items), "truncated": truncated, "tool": tool}

    if tool.startswith(("check_", "validate_", "verify_", "allowlist_")):
        violations = []
        target = root / path_s
        if path_s and target.is_file():
            text = read_text(target)
            if "TODO" in text:
                violations.append({"path": path_s, "rule": "todo", "message": "TODO found"})
        return {"ok": len(violations) == 0, "violations": violations, "count": len(violations), "tool": tool}

    if tool.startswith(("generate_", "suggest_", "render_", "plan_", "decompose_", "inject_")):
        body = f"# {tool}\n# root={root.name}\n# query={query or path_s}\n"
        return {"generated": body, "ok": True, "items": [{"text": body}], "tool": tool}

    if tool.startswith(("run_", "apply_", "execute_")):
        return {"ok": True, "exit_code": 0, "summary": f"{tool} dry-run on {root.name}", "tool": tool}

    if tool.startswith(("load_", "parse_", "fetch_")):
        target = root / path_s
        if target.is_file():
            content = read_text(target)
            return {"loaded": True, "content": content[:4000], "path": path_s, "tool": tool}
        # fall back to first text-ish file
        for f in files:
            if f.suffix in {".md", ".txt", ".py", ".go", ".json"} or f.name.upper().startswith("README"):
                return {
                    "loaded": True,
                    "content": read_text(f)[:4000],
                    "path": rel(f, root),
                    "tool": tool,
                }
        return {"loaded": False, "content": "", "path": path_s, "tool": tool}

    if tool.startswith(("add_", "record_", "update_", "mark_", "track_")):
        payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
        mid = hashlib.sha256(f"{tool}|{root}|{payload}".encode()).hexdigest()[:12]
        cache = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
        dest = cache / "naitv-mcp" / "team-metrics-collector"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / f"{mid}.json").write_text(payload + "\n", encoding="utf-8")
        return {"stored": True, "id": mid, "tool": tool}

    return {"ok": True, "tool": tool, "result": {"root": root.name, "files": len(files)}, "truncated": truncated}


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
