#!/usr/bin/env python3
"""symbol-navigator: AST symbol defs/refs for naitv-mcp (JSON stdin/stdout)."""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

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
