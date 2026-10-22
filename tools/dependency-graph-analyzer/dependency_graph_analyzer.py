#!/usr/bin/env python3
"""dependency-graph-analyzer: import graphs for Python/Go (JSON I/O)."""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 1_000_000
MAX_FILES = 2_000
MAX_FILE_BYTES = 256_000
DEFAULT_SKIP_DIRS = {
    "node_modules",
    ".git",
    "vendor",
    ".venv",
    "dist",
    "build",
    "__pycache__",
}
_GO_IMPORT = re.compile(
    r'^\s*(?:import\s+(?:\(\s*)?|")([A-Za-z0-9_./-]+)"?',
    re.MULTILINE,
)
_GO_IMPORT_LINE = re.compile(r'^\s*"([^"]+)"\s*$')
_GO_IMPORT_SINGLE = re.compile(r'^\s*import\s+(?:\w+\s+)?"([^"]+)"\s*$')


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


def iter_source_files(root: Path, depth: int, language: str) -> list[Path]:
    root = root.resolve()
    exts = {".py"} if language == "python" else {".go"} if language == "go" else {".py", ".go"}
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
            name = ent.name
            if ent.is_dir(follow_symlinks=False):
                if name in DEFAULT_SKIP_DIRS or name.startswith("."):
                    continue
                if d + 1 > depth:
                    continue
                walk(Path(ent.path), d + 1)
            elif ent.is_file(follow_symlinks=False):
                path = Path(ent.path)
                if path.suffix.lower() in exts:
                    out.append(path)

    walk(root, 0)
    return out


def module_name_for(path: Path, root: Path, language: str) -> str:
    rel = path.relative_to(root)
    if language == "python" or path.suffix == ".py":
        parts = list(rel.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else path.stem
    # go: directory package path
    return str(rel.parent).replace("\\", "/") if rel.parent != Path(".") else path.stem


def _py_imports(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append(alias.name.split(".")[0] if alias.name else alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.append(node.module.split(".")[0])
    # unique preserve order
    seen: set[str] = set()
    out: list[str] = []
    for m in found:
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _go_imports(text: str) -> list[str]:
    found: list[str] = []
    in_block = False
    for line in text.splitlines():
        if line.strip().startswith("import ("):
            in_block = True
            continue
        if in_block:
            if line.strip() == ")":
                in_block = False
                continue
            m = _GO_IMPORT_LINE.match(line)
            if m:
                found.append(m.group(1))
            continue
        m = _GO_IMPORT_SINGLE.match(line)
        if m:
            found.append(m.group(1))
    seen: set[str] = set()
    out: list[str] = []
    for m in found:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def build_graph(root: Path, *, language: str = "auto", depth: int = 3) -> dict[str, Any]:
    root = root.resolve()
    lang = language if language in ("python", "go", "auto") else "auto"
    files = iter_source_files(root, depth, lang)
    # Detect language from files if auto
    if lang == "auto":
        has_py = any(p.suffix == ".py" for p in files)
        has_go = any(p.suffix == ".go" for p in files)
        if has_py and not has_go:
            lang = "python"
        elif has_go and not has_py:
            lang = "go"
        else:
            lang = "python" if has_py else "go" if has_go else "python"

    nodes_set: set[str] = set()
    edges: list[dict[str, str]] = []
    edge_set: set[tuple[str, str]] = set()
    skipped: list[str] = []

    for path in files:
        file_lang = "python" if path.suffix == ".py" else "go"
        if language in ("python", "go") and file_lang != language:
            continue
        try:
            data = path.read_bytes()
        except OSError:
            skipped.append(str(path.relative_to(root)))
            continue
        if len(data) > MAX_FILE_BYTES:
            data = data[:MAX_FILE_BYTES]
        text = data.decode("utf-8", errors="replace")
        src = module_name_for(path, root, file_lang)
        nodes_set.add(src)
        imports = _py_imports(text) if file_lang == "python" else _go_imports(text)
        for dst in imports:
            # Keep external and internal; for python map local modules that exist as nodes later
            key = (src, dst)
            if key in edge_set:
                continue
            edge_set.add(key)
            edges.append({"from": src, "to": dst})
            nodes_set.add(dst)

    nodes = sorted(nodes_set)
    edges.sort(key=lambda e: (e["from"], e["to"]))
    return {
        "language": lang if language != "auto" else ("python" if any(p.suffix == ".py" for p in files) else "go" if files else "python"),
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "truncated": len(files) >= MAX_FILES,
        "skipped": sorted(skipped),
    }


def query_dependencies(root: Path, module: str, *, depth: int = 3, language: str = "auto") -> dict[str, Any]:
    graph = build_graph(root, language=language, depth=depth)
    imports = sorted({e["to"] for e in graph["edges"] if e["from"] == module})
    imported_by = sorted({e["from"] for e in graph["edges"] if e["to"] == module})
    return {
        "module": module,
        "imports": imports,
        "imported_by": imported_by,
        "found": module in graph["nodes"],
    }


def find_hubs(root: Path, *, limit: int = 10, depth: int = 3, language: str = "auto") -> dict[str, Any]:
    graph = build_graph(root, language=language, depth=depth)
    fan_in: dict[str, int] = defaultdict(int)
    for e in graph["edges"]:
        fan_in[e["to"]] += 1
    # include nodes with 0 fan-in? only those with edges into them, plus all nodes sorted
    modules = []
    for node in graph["nodes"]:
        modules.append({"module": node, "fan_in": int(fan_in.get(node, 0))})
    modules.sort(key=lambda m: (-m["fan_in"], m["module"]))
    limit = max(1, min(int(limit), 100))
    return {"modules": modules[:limit], "count": min(limit, len(modules))}


def export_graph(root: Path, *, fmt: str = "dot", depth: int = 3, language: str = "auto") -> dict[str, Any]:
    graph = build_graph(root, language=language, depth=depth)
    fmt = (fmt or "dot").lower()
    if fmt not in ("dot", "json"):
        _error("format must be 'dot' or 'json'")
    if fmt == "json":
        text = json.dumps(
            {"nodes": graph["nodes"], "edges": graph["edges"]},
            separators=(",", ":"),
            sort_keys=True,
        )
    else:
        lines = ["digraph imports {"]
        for e in graph["edges"]:
            frm = e["from"].replace('"', '\\"')
            to = e["to"].replace('"', '\\"')
            lines.append(f'  "{frm}" -> "{to}";')
        lines.append("}")
        text = "\n".join(lines) + "\n"
    return {"format": fmt, "graph": text, "node_count": graph["node_count"], "edge_count": graph["edge_count"]}


def main() -> None:
    tool = os.environ.get("TOOL_NAME", "").strip()
    if tool not in (
        "build_import_graph",
        "query_dependencies",
        "find_hubs",
        "export_graph",
    ):
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
    depth = int(data.get("depth", 3))
    language = data.get("language", "auto")
    if language is not None and not isinstance(language, str):
        _error("language must be a string")
    language = language or "auto"

    if tool == "build_import_graph":
        result = build_graph(root, language=language, depth=depth)
    elif tool == "query_dependencies":
        module = data.get("module")
        if not isinstance(module, str) or not module.strip():
            _error("module required")
        result = query_dependencies(
            root, module.strip(), depth=depth, language=language
        )
    elif tool == "find_hubs":
        limit = int(data.get("limit", 10))
        result = find_hubs(root, limit=limit, depth=depth, language=language)
    else:
        fmt = data.get("format", "dot")
        if fmt is not None and not isinstance(fmt, str):
            _error("format must be a string")
        result = export_graph(root, fmt=fmt or "dot", depth=depth, language=language)

    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
