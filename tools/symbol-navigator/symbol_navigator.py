#!/usr/bin/env python3
"""symbol-navigator: AST symbol defs/refs for naitv-mcp (JSON stdin/stdout)."""
from __future__ import annotations

import ast
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_SKIP_DIRS = {
    "node_modules", ".git", "vendor", ".venv", "dist", "build", "__pycache__",
}
SOURCE_EXTS = {".py", ".go"}


def normalize_skip_dirs(raw) -> set[str]:
    if raw is None or raw == "":
        return set(DEFAULT_SKIP_DIRS)
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("[") and s.endswith("]"):
            import json
            try:
                raw = json.loads(s)
            except json.JSONDecodeError:
                raw = [p.strip() for p in s.split(",") if p.strip()]
            else:
                pass
        else:
            raw = [p.strip() for p in s.split(",") if p.strip()]
    if isinstance(raw, (list, tuple, set)):
        out = {str(x).strip() for x in raw if str(x).strip()}
        return out or set(DEFAULT_SKIP_DIRS)
    return set(DEFAULT_SKIP_DIRS)


def iter_source_files(root: Path, depth: int, skip_dirs: set[str]) -> list[Path]:
    """Walk root; root is depth 0; do not descend past `depth`."""
    root = root.resolve()
    out: list[Path] = []

    def walk(dir_path: Path, d: int) -> None:
        try:
            with os.scandir(dir_path) as it:
                for ent in it:
                    name = ent.name
                    if ent.is_dir(follow_symlinks=False):
                        if name in skip_dirs or name.startswith("."):
                            continue
                        if d + 1 > depth:
                            continue
                        walk(Path(ent.path), d + 1)
                    elif ent.is_file(follow_symlinks=False):
                        if Path(name).suffix in SOURCE_EXTS:
                            out.append(Path(ent.path))
        except OSError:
            return

    walk(root, 0)
    return out


def git_commit(root: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root, capture_output=True, text=True, timeout=5, check=False,
        )
        if r.returncode == 0:
            return r.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None


def _git_dirty(root: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root, capture_output=True, text=True, timeout=5, check=False,
        )
        if r.returncode == 0 and r.stdout.strip():
            return hashlib.sha256(r.stdout.encode()).hexdigest()[:16]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def fingerprint(root: Path) -> str:
    commit = git_commit(root)
    if commit:
        dirty = _git_dirty(root)
        return f"{commit}:dirty:{dirty}" if dirty else commit
    index = root / ".git" / "index"
    if index.is_file():
        return f"index:{index.stat().st_mtime_ns}"
    h = hashlib.sha256()
    try:
        for ent in sorted(os.scandir(root), key=lambda e: e.name):
            h.update(ent.name.encode())
            try:
                h.update(str(ent.stat(follow_symlinks=False).st_mtime_ns).encode())
            except OSError:
                pass
    except OSError:
        h.update(b"empty")
    return f"top:{h.hexdigest()[:16]}"


def _ann(a: ast.expr | None) -> str:
    if a is None:
        return ""
    try:
        return ast.unparse(a)
    except Exception:
        return ""


def _args_sig(args: ast.arguments) -> str:
    parts: list[str] = []
    for a in args.posonlyargs:
        ann = _ann(a.annotation)
        parts.append(f"{a.arg}: {ann}" if ann else a.arg)
    if args.posonlyargs:
        parts.append("/")
    for a in args.args:
        ann = _ann(a.annotation)
        parts.append(f"{a.arg}: {ann}" if ann else a.arg)
    if args.vararg:
        parts.append("*" + args.vararg.arg)
    elif args.kwonlyargs:
        parts.append("*")
    for a in args.kwonlyargs:
        ann = _ann(a.annotation)
        parts.append(f"{a.arg}: {ann}" if ann else a.arg)
    if args.kwarg:
        parts.append("**" + args.kwarg.arg)
    return ", ".join(parts)


def _file_imports(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names.append(mod)
    return names


def extract_python_defs(path: Path) -> list[dict[str, Any]]:
    src = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src, filename=str(path))
    imports = _file_imports(tree)
    out: list[dict[str, Any]] = []

    def add(name, kind, node, signature):
        col = getattr(node, "col_offset", None)
        out.append({
            "name": name,
            "kind": kind,
            "file": str(path.resolve()),
            "line": getattr(node, "lineno", 0),
            "column": (col + 1) if col is not None else 0,
            "signature": signature,
            "receivers": [],
            "imports": list(imports),
        })

    def walk_body(body: list[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                add(node.name, "class", node, f"class {node.name}")
                for item in node.body:
                    if isinstance(item, ast.ClassDef):
                        walk_body([item])
                    elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        prefix = "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                        ret = _ann(item.returns)
                        sig = f"{prefix} {item.name}({_args_sig(item.args)})"
                        if ret:
                            sig += f" -> {ret}"
                        add(item.name, "method", item, sig)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                ret = _ann(node.returns)
                sig = f"{prefix} {node.name}({_args_sig(node.args)})"
                if ret:
                    sig += f" -> {ret}"
                add(node.name, "function", node, sig)

    walk_body(tree.body)
    return out
