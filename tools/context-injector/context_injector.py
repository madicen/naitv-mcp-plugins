#!/usr/bin/env python3
"""context-injector: code slices, snippets, file outlines (JSON I/O)."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 1_000_000
MAX_FILE_BYTES = 512_000
MAX_FILES = 500
DEFAULT_SKIP_DIRS = {
    "node_modules",
    ".git",
    "vendor",
    ".venv",
    "dist",
    "build",
    "__pycache__",
}
TEXT_EXTS = {".py", ".go", ".md", ".txt", ".json", ".ts", ".js"}


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


def resolve_file(root: Path, rel: str, *, must_exist: bool = True) -> Path | None:
    if not isinstance(rel, str) or not rel.strip():
        _error("path required")
    raw = Path(rel)
    if raw.is_absolute() or ".." in raw.parts:
        _error(f"path must be relative without '..': {rel}")
    path = (root / raw).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        _error(f"path escapes root_path: {rel}")
    if not path.is_file():
        if must_exist:
            return None
        return None
    return path


def _read_lines(path: Path) -> list[str]:
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        data = data[:MAX_FILE_BYTES]
    text = data.decode("utf-8", errors="replace")
    return text.splitlines()


def get_code_slice(root: Path, rel: str, start_line: int, end_line: int) -> dict[str, Any]:
    if start_line < 1 or end_line < start_line:
        _error("invalid start_line/end_line")
    if end_line - start_line > 500:
        _error("slice exceeds 500 lines")
    path = resolve_file(root, rel)
    if path is None:
        return {
            "code": "",
            "file": rel.replace("\\", "/"),
            "hash": "",
            "start_line": start_line,
            "end_line": end_line,
            "found": False,
        }
    lines = _read_lines(path)
    chunk = lines[start_line - 1 : end_line]
    code = "\n".join(chunk)
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]
    return {
        "code": code,
        "file": str(path.relative_to(root)).replace("\\", "/"),
        "hash": digest,
        "start_line": start_line,
        "end_line": min(end_line, len(lines)),
        "found": True,
    }


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", text.lower()) if len(t) > 1}


def _iter_files(root: Path, depth: int) -> list[Path]:
    out: list[Path] = []

    def walk(dir_path: Path, d: int) -> None:
        if len(out) >= MAX_FILES:
            return
        try:
            entries = list(os.scandir(dir_path))
        except OSError:
            return
        for ent in sorted(entries, key=lambda e: e.name):
            if len(out) >= MAX_FILES:
                return
            if ent.is_dir(follow_symlinks=False):
                if ent.name in DEFAULT_SKIP_DIRS or ent.name.startswith("."):
                    continue
                if d + 1 > depth:
                    continue
                walk(Path(ent.path), d + 1)
            elif ent.is_file(follow_symlinks=False):
                path = Path(ent.path)
                if path.suffix.lower() in TEXT_EXTS:
                    out.append(path)

    walk(root, 0)
    return out


def find_relevant_snippets(
    root: Path,
    query: str,
    *,
    max_tokens: int = 400,
    depth: int = 3,
) -> dict[str, Any]:
    qtokens = _tokenize(query)
    if not qtokens:
        return {"snippets": [], "total_tokens": 0}
    max_tokens = max(32, min(int(max_tokens), 4000))
    snippets: list[dict[str, Any]] = []
    total = 0
    for path in _iter_files(root, depth):
        try:
            lines = _read_lines(path)
        except OSError:
            continue
        # Window of 5 lines scored by token overlap
        best: tuple[float, int, int, str] | None = None
        for i in range(len(lines)):
            start = i
            end = min(len(lines), i + 5)
            window = "\n".join(lines[start:end])
            overlap = qtokens & _tokenize(window)
            if not overlap:
                continue
            score = len(overlap) / len(qtokens)
            if best is None or score > best[0]:
                best = (score, start + 1, end, window)
        if best is None:
            continue
        score, start, end, text = best
        approx = max(1, len(text.split()))
        if total + approx > max_tokens and snippets:
            break
        snippets.append(
            {
                "path": str(path.relative_to(root)),
                "start_line": start,
                "end_line": end,
                "text": text,
                "score": round(score, 6),
            }
        )
        total += approx
        if total >= max_tokens:
            break
    snippets.sort(key=lambda s: (-s["score"], s["path"], s["start_line"]))
    return {"snippets": snippets, "total_tokens": total}


def _python_outline(lines: list[str], text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    symbols: list[dict[str, Any]] = []
    ranges: list[dict[str, Any]] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return symbols, ranges
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "function"
            name = node.name
        elif isinstance(node, ast.ClassDef):
            kind = "class"
            name = node.name
        else:
            continue
        start = getattr(node, "lineno", 1)
        end = getattr(node, "end_lineno", start) or start
        symbols.append({"name": name, "kind": kind, "line": start})
        ranges.append({"name": name, "start_line": start, "end_line": end})
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    cstart = getattr(child, "lineno", start)
                    cend = getattr(child, "end_lineno", cstart) or cstart
                    symbols.append({"name": f"{name}.{child.name}", "kind": "method", "line": cstart})
                    ranges.append({"name": f"{name}.{child.name}", "start_line": cstart, "end_line": cend})
    symbols.sort(key=lambda s: (s["line"], s["name"]))
    ranges.sort(key=lambda r: (r["start_line"], r["name"]))
    return symbols, ranges


_GO_FUNC = re.compile(r"^func\s+(?:\([^)]+\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_GO_TYPE = re.compile(r"^type\s+([A-Za-z_][A-Za-z0-9_]*)\s+")


def _go_outline(lines: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    symbols: list[dict[str, Any]] = []
    ranges: list[dict[str, Any]] = []
    for i, line in enumerate(lines, start=1):
        m = _GO_FUNC.match(line)
        if m:
            symbols.append({"name": m.group(1), "kind": "function", "line": i})
            ranges.append({"name": m.group(1), "start_line": i, "end_line": i})
            continue
        m = _GO_TYPE.match(line)
        if m:
            symbols.append({"name": m.group(1), "kind": "type", "line": i})
            ranges.append({"name": m.group(1), "start_line": i, "end_line": i})
    return symbols, ranges


def get_file_outline(root: Path, rel: str) -> dict[str, Any]:
    path = resolve_file(root, rel)
    if path is None:
        return {
            "file": rel.replace("\\", "/"),
            "language": "other",
            "symbols": [],
            "line_ranges": [],
            "found": False,
        }
    lines = _read_lines(path)
    text = "\n".join(lines)
    suffix = path.suffix.lower()
    if suffix == ".py":
        symbols, ranges = _python_outline(lines, text)
        language = "python"
    elif suffix == ".go":
        symbols, ranges = _go_outline(lines)
        language = "go"
    else:
        symbols, ranges = [], []
        language = "other"
    return {
        "file": str(path.relative_to(root)).replace("\\", "/"),
        "language": language,
        "symbols": symbols,
        "line_ranges": ranges,
        "found": True,
    }


def main() -> None:
    tool = os.environ.get("TOOL_NAME", "").strip()
    if tool not in ("get_code_slice", "find_relevant_snippets", "get_file_outline"):
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

    try:
        if tool == "get_code_slice":
            path = data.get("path")
            start = data.get("start_line")
            end = data.get("end_line")
            if not isinstance(start, int) or not isinstance(end, int):
                _error("start_line and end_line required as integers")
            result = get_code_slice(root, path if isinstance(path, str) else "", start, end)
        elif tool == "find_relevant_snippets":
            query = data.get("query")
            if not isinstance(query, str) or not query.strip():
                _error("query required")
            max_tokens = int(data.get("max_tokens", 400))
            depth = int(data.get("depth", 3))
            result = find_relevant_snippets(
                root, query.strip(), max_tokens=max_tokens, depth=depth
            )
        else:
            path = data.get("path")
            if not isinstance(path, str):
                _error("path required")
            result = get_file_outline(root, path)
    except (TypeError, ValueError) as exc:
        _error(str(exc))

    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
