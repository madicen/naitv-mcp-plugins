#!/usr/bin/env python3
"""workspace-search: text + lightweight semantic search (JSON stdin/stdout)."""
from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 1_000_000
MAX_FILES = 2_000
MAX_FILE_BYTES = 256_000
MAX_MATCHES = 200
DEFAULT_SKIP_DIRS = {
    "node_modules",
    ".git",
    "vendor",
    ".venv",
    "dist",
    "build",
    "__pycache__",
}
TEXT_EXTS = {
    ".py",
    ".go",
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yml",
    ".yaml",
    ".rs",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".c",
    ".h",
    ".cpp",
    ".java",
    ".sh",
}


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


def normalize_skip_dirs(raw: Any) -> set[str]:
    if raw is None or raw == "":
        return set(DEFAULT_SKIP_DIRS)
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        return set(parts) or set(DEFAULT_SKIP_DIRS)
    if isinstance(raw, (list, tuple, set)):
        out = {str(x).strip() for x in raw if str(x).strip()}
        return out or set(DEFAULT_SKIP_DIRS)
    return set(DEFAULT_SKIP_DIRS)


def iter_files(root: Path, depth: int, skip_dirs: set[str], glob: str | None) -> list[Path]:
    root = root.resolve()
    out: list[Path] = []
    truncated = False

    def walk(dir_path: Path, d: int) -> None:
        nonlocal truncated
        if truncated or len(out) >= MAX_FILES:
            truncated = True
            return
        try:
            entries = list(os.scandir(dir_path))
        except OSError:
            return
        for ent in sorted(entries, key=lambda e: e.name):
            if truncated or len(out) >= MAX_FILES:
                truncated = True
                return
            name = ent.name
            if ent.is_dir(follow_symlinks=False):
                if name in skip_dirs or name.startswith("."):
                    continue
                if d + 1 > depth:
                    continue
                walk(Path(ent.path), d + 1)
            elif ent.is_file(follow_symlinks=False):
                path = Path(ent.path)
                if path.suffix.lower() not in TEXT_EXTS and path.name not in (
                    "Makefile",
                    "Dockerfile",
                    "README",
                ):
                    if glob is None:
                        continue
                if glob and not fnmatch.fnmatch(path.name, glob) and not fnmatch.fnmatch(
                    str(path.relative_to(root)), glob
                ):
                    continue
                out.append(path)

    walk(root, 0)
    return out


def _read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) > MAX_FILE_BYTES:
        data = data[:MAX_FILE_BYTES]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", text.lower()) if len(t) > 1}


def text_search(
    root: Path,
    pattern: str,
    *,
    depth: int = 3,
    skip_dirs: set[str] | None = None,
    glob: str | None = None,
) -> dict[str, Any]:
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        _error(f"invalid regex: {exc}")
    skip = skip_dirs if skip_dirs is not None else set(DEFAULT_SKIP_DIRS)
    files = iter_files(root, depth, skip, glob)
    matches: list[dict[str, Any]] = []
    truncated = len(files) >= MAX_FILES
    for path in files:
        text = _read_text(path)
        if text is None:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                matches.append(
                    {
                        "path": str(path.relative_to(root)),
                        "line": i,
                        "text": line[:400],
                    }
                )
                if len(matches) >= MAX_MATCHES:
                    truncated = True
                    break
        if len(matches) >= MAX_MATCHES:
            break
    matches.sort(key=lambda m: (m["path"], m["line"]))
    return {"matches": matches, "count": len(matches), "truncated": truncated}


def semantic_search(
    root: Path,
    query: str,
    *,
    limit: int = 10,
    depth: int = 3,
    skip_dirs: set[str] | None = None,
) -> dict[str, Any]:
    qtokens = _tokenize(query)
    if not qtokens:
        return {"results": [], "count": 0, "truncated": False}
    skip = skip_dirs if skip_dirs is not None else set(DEFAULT_SKIP_DIRS)
    files = iter_files(root, depth, skip, None)
    truncated = len(files) >= MAX_FILES
    scored: list[dict[str, Any]] = []
    for path in files:
        text = _read_text(path)
        if text is None:
            continue
        ftokens = _tokenize(text)
        if not ftokens:
            continue
        overlap = qtokens & ftokens
        if not overlap:
            continue
        # Jaccard-like score; path-name bonus for exact token hits.
        score = len(overlap) / len(qtokens | ftokens)
        name_tokens = _tokenize(path.stem)
        if qtokens & name_tokens:
            score += 0.25
        score = round(min(score, 1.0), 6)
        scored.append({"path": str(path.relative_to(root)), "score": score})
    scored.sort(key=lambda r: (-r["score"], r["path"]))
    limit = max(1, min(int(limit), 100))
    results = scored[:limit]
    return {"results": results, "count": len(results), "truncated": truncated}


def rank_results(query: str, candidates: list[Any]) -> dict[str, Any]:
    qtokens = _tokenize(query)
    ranked: list[dict[str, Any]] = []
    for i, cand in enumerate(candidates):
        if isinstance(cand, str):
            path = cand
            extra: dict[str, Any] = {}
        elif isinstance(cand, dict) and isinstance(cand.get("path"), str):
            path = cand["path"]
            extra = {k: v for k, v in cand.items() if k != "path"}
        else:
            _error("candidates must be strings or objects with path")
        ctokens = _tokenize(path) | _tokenize(json.dumps(extra, sort_keys=True))
        if not qtokens:
            score = 0.0
        else:
            overlap = qtokens & ctokens
            score = round(len(overlap) / len(qtokens), 6) if qtokens else 0.0
        row = {"path": path, "score": score, "index": i}
        ranked.append(row)
    ranked.sort(key=lambda r: (-r["score"], r["index"], r["path"]))
    return {"ranked": ranked, "count": len(ranked)}


def main() -> None:
    tool = os.environ.get("TOOL_NAME", "").strip()
    if tool not in ("semantic_search", "text_search", "rank_results"):
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

    if tool == "rank_results":
        query = data.get("query")
        candidates = data.get("candidates")
        if not isinstance(query, str) or not query.strip():
            _error("query required")
        if not isinstance(candidates, list):
            _error("candidates must be an array")
        if len(candidates) > 500:
            _error("candidates exceeds 500")
        result = rank_results(query.strip(), candidates)
    else:
        root_raw = data.get("root_path")
        if not root_raw:
            _error("root_path required")
        if not isinstance(root_raw, str):
            _error("root_path must be a string")
        root = validate_root_path(root_raw)
        depth = int(data.get("depth", 3))
        skip_dirs = normalize_skip_dirs(data.get("skip_dirs"))
        if tool == "text_search":
            pattern = data.get("pattern")
            if not isinstance(pattern, str) or not pattern:
                _error("pattern required")
            glob = data.get("glob")
            if glob is not None and not isinstance(glob, str):
                _error("glob must be a string")
            result = text_search(
                root, pattern, depth=depth, skip_dirs=skip_dirs, glob=glob
            )
        else:
            query = data.get("query")
            if not isinstance(query, str) or not query.strip():
                _error("query required")
            limit = int(data.get("limit", 10))
            result = semantic_search(
                root, query.strip(), limit=limit, depth=depth, skip_dirs=skip_dirs
            )

    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
