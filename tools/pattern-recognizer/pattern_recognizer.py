#!/usr/bin/env python3
"""pattern-recognizer: repeated snippets / imports / function bodies (JSON I/O)."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 1_000_000
MAX_FILES = 500
MAX_FILE_BYTES = 64_000
MAX_PATTERNS = 100
SKIP = {".git", "node_modules", "vendor", ".venv", "__pycache__", "dist", "build"}
CODE_EXTS = {".py", ".go"}
TOOLS = {
    "find_pattern_instances",
    "detect_repeated_patterns",
    "rank_examples",
    "pattern_summary",
}
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_GO_IMPORT_SINGLE = re.compile(r'^\s*import\s+(?:\w+\s+)?"([^"]+)"\s*$')
_GO_IMPORT_LINE = re.compile(r'^\s*"([^"]+)"\s*$')


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
        return max(1, min(int(n), MAX_PATTERNS))
    except (TypeError, ValueError):
        return default


def _norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _body_fingerprint(text: str) -> str:
    return hashlib.sha256(_norm_ws(text).encode("utf-8")).hexdigest()[:12]


def _code_files(root: Path, depth: int) -> tuple[list[Path], bool]:
    all_files = iter_files(root, depth)
    files = [f for f in all_files if f.suffix.lower() in CODE_EXTS]
    return files, len(all_files) >= MAX_FILES


def _py_functions(text: str) -> list[tuple[str, int, str]]:
    """Return (name, lineno, body) for top-level and method defs; name from AST only."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    out: list[tuple[str, int, str]] = []
    lines = text.splitlines()

    def add(node: ast.AST, name: str) -> None:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return
        start = getattr(node, "lineno", 1)
        end = getattr(node, "end_lineno", start) or start
        body = "\n".join(lines[start - 1 : end])
        if len(_norm_ws(body)) < 20:
            return
        out.append((name, start, body))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add(node, node.name)
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add(child, f"{node.name}.{child.name}")
    return out


def _go_functions(text: str) -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^func\s+(?:\([^)]+\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\(", lines[i])
        if not m:
            i += 1
            continue
        name = m.group(1)
        start = i + 1
        # lazy: brace depth until matching close
        depth = 0
        started = False
        j = i
        while j < len(lines):
            for ch in lines[j]:
                if ch == "{":
                    depth += 1
                    started = True
                elif ch == "}":
                    depth -= 1
            if started and depth <= 0:
                break
            j += 1
        body = "\n".join(lines[i : j + 1])
        if len(_norm_ws(body)) >= 20:
            out.append((name, start, body))
        i = j + 1
    return out


def _import_keys(text: str, suffix: str) -> list[tuple[str, int]]:
    """Literal import strings with line numbers."""
    found: list[tuple[str, int]] = []
    if suffix == ".py":
        for i, line in enumerate(text.splitlines(), start=1):
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                key = _norm_ws(s)
                if key:
                    found.append((key, i))
        return found
    in_block = False
    for i, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("import ("):
            in_block = True
            continue
        if in_block:
            if line.strip() == ")":
                in_block = False
                continue
            m = _GO_IMPORT_LINE.match(line)
            if m:
                found.append((f'import "{m.group(1)}"', i))
            continue
        m = _GO_IMPORT_SINGLE.match(line)
        if m:
            found.append((f'import "{m.group(1)}"', i))
    return found


def _collect_locations(
    root: Path, depth: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Build import and body location records from real file tokens only."""
    files, truncated = _code_files(root, depth)
    imports: list[dict[str, Any]] = []
    bodies: list[dict[str, Any]] = []
    for path in files:
        r = rel(path, root)
        text = read_text(path)
        for key, line in _import_keys(text, path.suffix.lower()):
            imports.append(
                {
                    "kind": "import",
                    "name": key[:200],
                    "path": r,
                    "line": line,
                    "fp": _body_fingerprint(key),
                }
            )
        funcs = (
            _py_functions(text) if path.suffix.lower() == ".py" else _go_functions(text)
        )
        for name, line, body in funcs:
            bodies.append(
                {
                    "kind": "body",
                    "name": name,
                    "path": r,
                    "line": line,
                    "fp": _body_fingerprint(body),
                }
            )
    return imports, bodies, truncated


def find_pattern_instances(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    query = str(
        data.get("query") or data.get("pattern") or data.get("pattern_id") or ""
    ).strip()
    limit = _limit(data.get("limit", 20))
    depth = int(data.get("depth", 3))
    files, truncated = _code_files(root, depth)
    items: list[dict[str, Any]] = []
    q = query
    for path in files:
        r = rel(path, root)
        text = read_text(path)
        if q:
            for i, line in enumerate(text.splitlines(), start=1):
                if q not in line:
                    continue
                # name = first identifier on the line that contains the query, else query itself if it appears
                name = q if _IDENT.fullmatch(q) else ""
                if not name:
                    for m in _IDENT.finditer(line):
                        if q in m.group(0) or m.group(0) in q:
                            name = m.group(0)
                            break
                    if not name:
                        m2 = _IDENT.search(line)
                        name = m2.group(0) if m2 else q
                items.append(
                    {
                        "path": r,
                        "name": name,
                        "line": i,
                        "score": 1.0,
                    }
                )
                if len(items) >= limit:
                    break
        else:
            # no query: list top-level defs as pattern candidates
            funcs = (
                _py_functions(text)
                if path.suffix.lower() == ".py"
                else _go_functions(text)
            )
            for name, line, _body in funcs:
                items.append({"path": r, "name": name, "line": line, "score": 0.5})
                if len(items) >= limit:
                    break
        if len(items) >= limit:
            break
    return {
        "items": items[:limit],
        "count": len(items[:limit]),
        "truncated": truncated,
        "tool": "find_pattern_instances",
    }


def detect_repeated_patterns(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    limit = _limit(data.get("limit", 20))
    depth = int(data.get("depth", 3))
    try:
        min_occ = max(2, int(data.get("min_occurrences", 2)))
    except (TypeError, ValueError):
        min_occ = 2
    imports, bodies, truncated = _collect_locations(root, depth)
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for loc in imports + bodies:
        buckets[f"{loc['kind']}:{loc['fp']}"].append(loc)
    patterns: list[dict[str, Any]] = []
    for key, locs in buckets.items():
        if len(locs) < min_occ:
            continue
        kind = locs[0]["kind"]
        # representative name: most common literal name among locs
        name_counts: dict[str, int] = defaultdict(int)
        for loc in locs:
            name_counts[loc["name"]] += 1
        name = sorted(name_counts.items(), key=lambda x: (-x[1], x[0]))[0][0]
        patterns.append(
            {
                "kind": kind,
                "name": name,
                "fp": locs[0]["fp"],
                "count": len(locs),
                "locations": [
                    {"path": loc["path"], "name": loc["name"], "line": loc["line"]}
                    for loc in sorted(locs, key=lambda x: (x["path"], x["line"]))[
                        :20
                    ]
                ],
            }
        )
    patterns.sort(key=lambda p: (-p["count"], p["kind"], p["name"], p["fp"]))
    patterns = patterns[:limit]
    return {
        "ok": True,
        "tool": "detect_repeated_patterns",
        "items": patterns,
        "count": len(patterns),
        "truncated": truncated,
        "result": {"patterns": patterns, "min_occurrences": min_occ},
    }


def rank_examples(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    limit = _limit(data.get("limit", 20))
    detected = detect_repeated_patterns(root, {**data, "min_occurrences": 1})
    # rank: prefer higher frequency; expand locations as ranked examples
    examples: list[dict[str, Any]] = []
    query = str(
        data.get("query") or data.get("pattern") or data.get("pattern_id") or ""
    ).strip()
    for pat in detected["items"]:
        if query and query not in pat["name"] and query not in pat.get("fp", ""):
            # also allow query match against location paths
            if not any(query in loc["path"] for loc in pat["locations"]):
                continue
        for loc in pat["locations"]:
            examples.append(
                {
                    "path": loc["path"],
                    "name": loc["name"],
                    "line": loc["line"],
                    "kind": pat["kind"],
                    "score": float(pat["count"]),
                }
            )
    examples.sort(key=lambda e: (-e["score"], e["path"], e["line"], e["name"]))
    examples = examples[:limit]
    return {
        "ok": True,
        "tool": "rank_examples",
        "items": examples,
        "count": len(examples),
        "truncated": detected["truncated"],
        "result": {"examples": examples},
    }


def pattern_summary(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    limit = _limit(data.get("limit", 20))
    detected = detect_repeated_patterns(root, {**data, "min_occurrences": 2})
    query = str(
        data.get("query") or data.get("pattern") or data.get("pattern_id") or ""
    ).strip()
    items = detected["items"]
    if query:
        items = [
            p
            for p in items
            if query in p["name"]
            or any(query in loc["path"] or query in loc["name"] for loc in p["locations"])
        ]
        # if no repeated match, fall back to find instances summary
        if not items:
            found = find_pattern_instances(root, data)
            return {
                "items": found["items"],
                "count": found["count"],
                "truncated": found["truncated"],
                "tool": "pattern_summary",
                "instance_count": found["count"],
                "summary": f"instances={found['count']}",
            }
    items = items[:limit]
    total_instances = sum(int(p["count"]) for p in items)
    return {
        "items": items,
        "count": len(items),
        "truncated": detected["truncated"],
        "tool": "pattern_summary",
        "instance_count": total_instances,
        "summary": f"patterns={len(items)} instances={total_instances}",
    }


def handle(tool: str, root: Path, data: dict[str, Any]) -> dict[str, Any]:
    if tool == "find_pattern_instances":
        return find_pattern_instances(root, data)
    if tool == "detect_repeated_patterns":
        return detect_repeated_patterns(root, data)
    if tool == "rank_examples":
        return rank_examples(root, data)
    if tool == "pattern_summary":
        return pattern_summary(root, data)
    # scaffold branch coverage for L1 fake-tool tests
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
