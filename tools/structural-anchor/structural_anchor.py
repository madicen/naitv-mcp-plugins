#!/usr/bin/env python3
"""structural-anchor: codebase map for naitv-mcp (JSON stdin/stdout)."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_SKIP_DIRS = {
    "node_modules",
    ".git",
    "vendor",
    ".venv",
    "dist",
    "build",
    "__pycache__",
}
SOURCE_EXTS = {".py", ".go"}


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
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if r.returncode == 0:
            return r.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None


def fingerprint(root: Path) -> str:
    commit = git_commit(root)
    if commit:
        return commit
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


def cache_dir() -> Path:
    return Path.home() / ".cache" / "naitv-mcp" / "structural-anchor"


def bin_dir() -> Path:
    return Path.home() / ".cache" / "naitv-mcp" / "bin"


def cache_key(root: Path, depth: int, skip_dirs: set[str], fp: str) -> str:
    raw = f"{root.resolve()}|{depth}|{','.join(sorted(skip_dirs))}|{fp}"
    return hashlib.sha256(raw.encode()).hexdigest()


def load_cache(key: str) -> dict[str, Any] | None:
    p = cache_dir() / f"{key}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_cache(key: str, payload: dict[str, Any]) -> None:
    d = cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps(payload), encoding="utf-8")


def ensure_go_symbols_bin(src_dir: Path) -> Path | None:
    """Build go_symbols into cache bin if needed. None if go unavailable."""
    out = bin_dir() / "go-symbols"
    main_go = src_dir / "main.go"
    if not main_go.is_file():
        return None
    need = True
    if out.is_file():
        need = out.stat().st_mtime_ns < main_go.stat().st_mtime_ns
    if not need:
        return out
    bin_dir().mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["go", "build", "-o", str(out), "."],
        cwd=src_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode != 0:
        return None
    return out if out.is_file() else None


def cyclomatic_python(node: ast.AST) -> float:
    decisions = 0
    for n in ast.walk(node):
        if isinstance(n, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With, ast.Assert)):
            decisions += 1
        elif isinstance(n, ast.BoolOp):
            decisions += max(0, len(n.values) - 1)
        elif isinstance(n, ast.comprehension):
            decisions += 1
    return float(decisions + 1)


def _ann(a: ast.expr | None) -> str:
    if a is None:
        return ""
    try:
        return ast.unparse(a)
    except Exception:
        return ""


def _args_sig(args: ast.arguments) -> str:
    parts: list[str] = []
    for a in args.args:
        ann = _ann(a.annotation)
        parts.append(f"{a.arg}: {ann}" if ann else a.arg)
    return ", ".join(parts)


def extract_python_symbols(path: Path) -> tuple[list[dict[str, Any]], list[float], int]:
    src = path.read_text(encoding="utf-8", errors="replace")
    lines = src.count("\n") + (0 if src.endswith("\n") or not src else 1)
    tree = ast.parse(src, filename=str(path))
    symbols: list[dict[str, Any]] = []
    complexities: list[float] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            symbols.append(
                {
                    "name": node.name,
                    "kind": "class",
                    "signature": f"class {node.name}",
                    "line": node.lineno,
                }
            )
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    prefix = "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                    ret = _ann(item.returns)
                    sig = f"{prefix} {item.name}({_args_sig(item.args)})"
                    if ret:
                        sig += f" -> {ret}"
                    symbols.append(
                        {"name": item.name, "kind": "method", "signature": sig, "line": item.lineno}
                    )
                    complexities.append(cyclomatic_python(item))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            ret = _ann(node.returns)
            sig = f"{prefix} {node.name}({_args_sig(node.args)})"
            if ret:
                sig += f" -> {ret}"
            symbols.append(
                {"name": node.name, "kind": "function", "signature": sig, "line": node.lineno}
            )
            complexities.append(cyclomatic_python(node))
    return symbols, complexities, lines
