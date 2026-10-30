#!/usr/bin/env python3
"""documentation-enforcer: find undocumented defs, check/stub docs, coverage."""
from __future__ import annotations

import ast
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
CODE_EXTS = {".py", ".go"}
TOOLS = {
    "find_undocumented",
    "check_doc_comments",
    "generate_doc_stub",
    "doc_coverage_report",
}

_GO_FUNC = re.compile(
    r"^func\s+(?:\([^)]+\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\("
)
_GO_DOC = re.compile(r"^//")


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


def _py_defs(text: str) -> list[tuple[str, int, bool]]:
    """(name, lineno, has_doc)."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    out: list[tuple[str, int, bool]] = []

    def add(node: ast.AST, name: str) -> None:
        doc = ast.get_docstring(node)  # type: ignore[arg-type]
        out.append((name, getattr(node, "lineno", 1), bool(doc and doc.strip())))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add(node, node.name)
        elif isinstance(node, ast.ClassDef):
            add(node, node.name)
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add(child, f"{node.name}.{child.name}")
    return out


def _go_defs(text: str) -> list[tuple[str, int, bool]]:
    lines = text.splitlines()
    out: list[tuple[str, int, bool]] = []
    i = 0
    while i < len(lines):
        m = _GO_FUNC.match(lines[i])
        if not m:
            i += 1
            continue
        name = m.group(1)
        # preceding contiguous // comments count as docs
        j = i - 1
        has_doc = False
        while j >= 0 and _GO_DOC.match(lines[j].lstrip()):
            has_doc = True
            j -= 1
        out.append((name, i + 1, has_doc))
        i += 1
    return out


def _collect_defs(root: Path, depth: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in iter_files(root, depth):
        if path.suffix.lower() not in CODE_EXTS:
            continue
        text = read_text(path)
        defs = _py_defs(text) if path.suffix.lower() == ".py" else _go_defs(text)
        r = rel(path, root)
        for name, line, has_doc in defs:
            items.append(
                {
                    "path": r,
                    "name": name,
                    "line": line,
                    "documented": has_doc,
                }
            )
    return items


def find_undocumented(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    limit = max(1, min(int(data.get("limit", 20)), 100))
    query = str(data.get("query") or data.get("symbol") or "").strip()
    undoc = [d for d in _collect_defs(root, depth) if not d["documented"]]
    if query:
        q = query.lower()
        undoc = [d for d in undoc if q in d["name"].lower() or q in d["path"].lower()]
    undoc = undoc[:limit]
    return {
        "items": undoc,
        "count": len(undoc),
        "tool": "find_undocumented",
    }


def check_doc_comments(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    path_s = str(data.get("path") or data.get("file") or "").strip()
    violations: list[dict[str, Any]] = []
    defs = _collect_defs(root, depth)
    if path_s:
        defs = [d for d in defs if d["path"] == path_s.replace("\\", "/")]
    for d in defs:
        if not d["documented"]:
            violations.append(
                {
                    "path": d["path"],
                    "name": d["name"],
                    "line": d["line"],
                    "rule": "missing_doc",
                    "message": f"{d['name']} has no docstring/comment",
                }
            )
    return {
        "ok": len(violations) == 0,
        "violations": violations[:100],
        "count": len(violations),
        "tool": "check_doc_comments",
    }


def generate_doc_stub(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    symbol = str(data.get("symbol") or data.get("query") or data.get("name") or "").strip()
    path_s = str(data.get("path") or data.get("file") or "").strip()
    depth = int(data.get("depth", 3))
    target = None
    for d in _collect_defs(root, depth):
        if symbol and d["name"] != symbol and not d["name"].endswith("." + symbol):
            continue
        if path_s and d["path"] != path_s.replace("\\", "/"):
            continue
        if symbol or path_s:
            target = d
            break
    if target is None and symbol:
        # no match — still emit a stub named after the request
        target = {"name": symbol, "path": path_s or "unknown", "line": 1}
    if target is None:
        return {
            "ok": False,
            "generated": "",
            "items": [],
            "tool": "generate_doc_stub",
        }
    name = target["name"]
    stub = f'"""TODO: document {name}."""'
    if str(target.get("path", "")).endswith(".go"):
        stub = f"// {name} ..."
    body = f"# generate_doc_stub\n# path={target.get('path')}\n# symbol={name}\n{stub}\n"
    return {
        "ok": True,
        "generated": body,
        "items": [{"name": name, "path": target.get("path"), "text": stub}],
        "tool": "generate_doc_stub",
    }


def doc_coverage_report(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    defs = _collect_defs(root, depth)
    total = len(defs)
    documented = sum(1 for d in defs if d["documented"])
    pct = round(100.0 * documented / total, 1) if total else 100.0
    undoc = [d for d in defs if not d["documented"]][:20]
    return {
        "total": total,
        "documented": documented,
        "undocumented": total - documented,
        "coverage_pct": pct,
        "items": undoc,
        "count": len(undoc),
        "tool": "doc_coverage_report",
    }


def handle(tool: str, root: Path, data: dict[str, Any]) -> dict[str, Any]:
    if tool == "find_undocumented":
        return find_undocumented(root, data)
    if tool == "check_doc_comments":
        return check_doc_comments(root, data)
    if tool == "generate_doc_stub":
        return generate_doc_stub(root, data)
    if tool == "doc_coverage_report":
        return doc_coverage_report(root, data)
    # harness smoke for unknown prefixes
    return {"ok": True, "tool": tool, "result": {"root": root.name}}


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
