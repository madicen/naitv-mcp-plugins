#!/usr/bin/env python3
"""doc-scraper: local markdown README/docs only — no HTTP (JSON I/O)."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 1_000_000
MAX_FILES = 500
MAX_FILE_BYTES = 64_000
MAX_CONTENT = 4000
SKIP = {".git", "node_modules", "vendor", ".venv", "__pycache__", "dist", "build"}
MD_EXTS = {".md", ".markdown", ".mdx", ".txt"}
TOOLS = {
    "fetch_and_parse",
    "extract_sections",
    "search_doc_index",
}
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


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


def _limit(n: Any, default: int = 20) -> int:
    try:
        return max(1, min(int(n), 100))
    except (TypeError, ValueError):
        return default


def _is_doc(path: Path) -> bool:
    name = path.name
    if name.upper().startswith("README"):
        return True
    return path.suffix.lower() in MD_EXTS


def _doc_files(root: Path, depth: int) -> tuple[list[Path], bool]:
    all_files = iter_files(root, depth)
    docs = [f for f in all_files if _is_doc(f)]
    return docs, len(all_files) >= MAX_FILES


def _safe_rel_path(root: Path, path_s: str) -> Path | None:
    raw = Path(path_s)
    if raw.is_absolute() or ".." in raw.parts:
        return None
    target = (root / raw).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target if target.is_file() else None


def _parse_sections(text: str) -> list[dict[str, Any]]:
    """Extract markdown headings; titles are literal heading text from the file."""
    sections: list[dict[str, Any]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _HEADING.match(lines[i])
        if not m:
            i += 1
            continue
        level = len(m.group(1))
        title = m.group(2).strip()
        start_line = i + 1
        j = i + 1
        # body ends at the next heading of any level so nested ## are separate sections
        while j < len(lines) and not _HEADING.match(lines[j]):
            j += 1
        body = "\n".join(lines[i + 1 : j]).strip()
        sections.append(
            {
                "name": title,
                "level": level,
                "line": start_line,
                "body": body[:2000],
            }
        )
        i = j
    return sections


def fetch_and_parse(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    path_s = str(data.get("path") or data.get("file") or "README.md").strip()
    target = _safe_rel_path(root, path_s) if path_s else None
    if target is None or not _is_doc(target):
        # prefer README*, then first markdown under root
        docs, _ = _doc_files(root, depth)
        readmes = [f for f in docs if f.name.upper().startswith("README")]
        pick = (readmes or docs)
        if not pick:
            return {
                "loaded": False,
                "content": "",
                "path": path_s,
                "sections": [],
                "tool": "fetch_and_parse",
            }
        target = pick[0]
        path_s = rel(target, root)
    else:
        path_s = rel(target, root)
    content = read_text(target)
    sections = _parse_sections(content)
    return {
        "loaded": True,
        "content": content[:MAX_CONTENT],
        "path": path_s,
        "sections": [
            {"name": s["name"], "level": s["level"], "line": s["line"]}
            for s in sections
        ],
        "tool": "fetch_and_parse",
    }


def extract_sections(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    limit = _limit(data.get("limit", 20))
    path_s = str(data.get("path") or data.get("file") or "").strip()
    truncated = False
    files: list[Path] = []
    if path_s:
        target = _safe_rel_path(root, path_s)
        if target is not None and _is_doc(target):
            files = [target]
    if not files:
        files, truncated = _doc_files(root, depth)
    items: list[dict[str, Any]] = []
    for path in files:
        r = rel(path, root)
        for sec in _parse_sections(read_text(path)):
            items.append(
                {
                    "path": r,
                    "name": sec["name"],
                    "line": sec["line"],
                    "level": sec["level"],
                }
            )
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break
    return {
        "items": items[:limit],
        "count": len(items[:limit]),
        "truncated": truncated,
        "tool": "extract_sections",
    }


def search_doc_index(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    query = str(data.get("query") or data.get("pattern") or data.get("text") or "").strip()
    depth = int(data.get("depth", 3))
    limit = _limit(data.get("limit", 20))
    docs, truncated = _doc_files(root, depth)
    items: list[dict[str, Any]] = []
    q = query.lower()
    for path in docs:
        r = rel(path, root)
        text = read_text(path)
        sections = _parse_sections(text)
        if not sections and (not q or q in text.lower() or q in r.lower()):
            items.append(
                {
                    "path": r,
                    "name": path.stem,
                    "line": 1,
                    "score": 1.0 if not q else round(min(1.0, len(q) / max(len(r), 1)), 4),
                }
            )
            if len(items) >= limit:
                break
            continue
        for sec in sections:
            hay = f"{sec['name']}\n{sec['body']}".lower()
            if q and q not in hay and q not in r.lower():
                continue
            score = 1.0
            if q:
                if q in sec["name"].lower():
                    score = 1.0
                elif q in sec["body"].lower():
                    score = 0.75
                else:
                    score = 0.4
            items.append(
                {
                    "path": r,
                    "name": sec["name"],
                    "line": sec["line"],
                    "score": score,
                }
            )
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break
    items.sort(key=lambda x: (-float(x.get("score", 0)), x["path"], x["line"]))
    return {
        "items": items[:limit],
        "count": len(items[:limit]),
        "truncated": truncated,
        "tool": "search_doc_index",
    }


def handle(tool: str, root: Path, data: dict[str, Any]) -> dict[str, Any]:
    if tool == "fetch_and_parse":
        return fetch_and_parse(root, data)
    if tool == "extract_sections":
        return extract_sections(root, data)
    if tool == "search_doc_index":
        return search_doc_index(root, data)
    depth = int(data.get("depth", 3))
    files = iter_files(root, depth)
    return {
        "ok": True,
        "tool": tool,
        "result": {"root": root.name, "files": len(files)},
        "truncated": len(files) >= MAX_FILES,
    }


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
