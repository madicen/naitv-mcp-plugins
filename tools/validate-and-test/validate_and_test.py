#!/usr/bin/env python3
"""validate-and-test: detect build system + dry-run validation (JSON I/O)."""
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
SKIP = {".git", "node_modules", "vendor", ".venv", "__pycache__", "dist", "build"}
TOOLS = {
    "detect_build_system",
    "run_validation",
    "summarize_failures",
}
# Marker filename → build system id (literal filenames only).
ROOT_MARKERS: list[tuple[str, tuple[str, ...]]] = [
    ("go", ("go.mod",)),
    ("python", ("pyproject.toml", "setup.py", "requirements.txt", "setup.cfg")),
    ("make", ("Makefile", "makefile", "GNUmakefile")),
    ("npm", ("package.json",)),
]
_FAIL_LINE = re.compile(
    r"(?i)\bFAIL\b|\bFAILED\b|\berror:\b|--- FAIL:|AssertionError|panic:"
)
_GO_TEST_FUNC = re.compile(r"^func\s+(Test[A-Za-z0-9_]*)\s*\(")
_PY_TEST_DEF = re.compile(r"^def\s+(test_[A-Za-z0-9_]*)\s*\(")


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


def _scan_markers(root: Path) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    marker_to_sys = {name: sys_id for sys_id, names in ROOT_MARKERS for name in names}
    try:
        entries = [
            ent for ent in os.scandir(root) if ent.is_file(follow_symlinks=False)
        ]
    except OSError:
        return []
    for ent in sorted(entries, key=lambda e: e.name):
        sys_id = marker_to_sys.get(ent.name)
        if sys_id is None:
            continue
        found.append((sys_id, ent.name))
    return found


def _commands_for(system: str) -> list[str]:
    if system == "go":
        return ["go test ./...", "go vet ./...", "go build ./..."]
    if system == "python":
        return ["python3 -m pytest -q", "python3 -m compileall -q ."]
    if system == "make":
        return ["make test", "make check", "make"]
    if system == "npm":
        return ["npm test", "npm run lint"]
    return []


def detect_build_system(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    pairs = _scan_markers(root)
    if not pairs:
        return {
            "ok": True,
            "tool": "detect_build_system",
            "build_system": "unknown",
            "config_files": [],
            "commands": [],
            "result": {"build_system": "unknown", "config_files": []},
        }
    # Prefer first marker by ROOT_MARKERS priority order
    priority = {sys_id: i for i, (sys_id, _) in enumerate(ROOT_MARKERS)}
    pairs.sort(key=lambda p: (priority.get(p[0], 99), p[1]))
    system = pairs[0][0]
    config_files = sorted({name for sys_id, name in pairs if sys_id == system})
    commands = _commands_for(system)
    return {
        "ok": True,
        "tool": "detect_build_system",
        "build_system": system,
        "config_files": config_files,
        "commands": commands,
        "result": {
            "build_system": system,
            "config_files": config_files,
            "commands": commands,
        },
    }


def _is_test_file(path: Path) -> bool:
    name = path.name
    if path.suffix == ".py":
        return name.startswith("test_") or name.endswith("_test.py")
    if path.suffix == ".go":
        return name.endswith("_test.go")
    if path.suffix in {".js", ".ts"}:
        return ".test." in name or ".spec." in name
    return False


def _list_test_symbols(path: Path, text: str) -> list[str]:
    names: list[str] = []
    if path.suffix == ".go":
        for line in text.splitlines():
            m = _GO_TEST_FUNC.match(line)
            if m:
                names.append(m.group(1))
    elif path.suffix == ".py":
        for line in text.splitlines():
            m = _PY_TEST_DEF.match(line)
            if m:
                names.append(m.group(1))
    return names


def run_validation(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    """Cheap dry-run: list test files / symbols — do not execute suites."""
    depth = int(data.get("depth", 3))
    limit = _limit(data.get("limit", 50))
    detected = detect_build_system(root, data)
    system = detected["build_system"]
    files = iter_files(root, depth)
    truncated = len(files) >= MAX_FILES
    test_files = [f for f in files if _is_test_file(f)]
    items: list[dict[str, Any]] = []
    for path in test_files[:limit]:
        r = rel(path, root)
        text = read_text(path)
        symbols = _list_test_symbols(path, text)
        items.append(
            {
                "path": r,
                "name": path.name,
                "symbols": symbols[:50],
                "symbol_count": len(symbols),
            }
        )
    summary = (
        f"dry-run {system}: {len(test_files)} test file(s) listed"
        f"{' (truncated)' if truncated else ''}"
    )
    return {
        "ok": True,
        "exit_code": 0,
        "summary": summary,
        "tool": "run_validation",
        "build_system": system,
        "items": items,
        "count": len(items),
        "truncated": truncated,
        "dry_run": True,
    }


def _parse_fail_lines(text: str, *, source: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if not _FAIL_LINE.search(line):
            continue
        # keep the literal line content (trimmed); path = source path if file-like
        items.append(
            {
                "path": source,
                "line": i,
                "name": line.strip()[:240],
            }
        )
    return items


def summarize_failures(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    limit = _limit(data.get("limit", 20))
    depth = int(data.get("depth", 3))
    log_text = data.get("log") or data.get("text") or data.get("results")
    items: list[dict[str, Any]] = []
    if isinstance(log_text, str) and log_text.strip():
        items.extend(_parse_fail_lines(log_text, source="log"))
    elif isinstance(log_text, list):
        # results[] of strings or dicts with message
        blob_parts: list[str] = []
        for row in log_text:
            if isinstance(row, str):
                blob_parts.append(row)
            elif isinstance(row, dict):
                for key in ("message", "summary", "name", "error", "text"):
                    val = row.get(key)
                    if isinstance(val, str):
                        blob_parts.append(val)
                        break
        items.extend(_parse_fail_lines("\n".join(blob_parts), source="log"))
    else:
        # scan fixture-like log files under root for FAIL lines
        path_s = str(data.get("path") or data.get("file") or "").strip()
        candidates: list[Path] = []
        if path_s and ".." not in Path(path_s).parts and not Path(path_s).is_absolute():
            target = root / path_s
            if target.is_file():
                candidates = [target]
        if not candidates:
            for f in iter_files(root, depth):
                name = f.name.lower()
                if (
                    name.endswith(".log")
                    or "fail" in name
                    or name in {"test-output.txt", "pytest.log"}
                ):
                    candidates.append(f)
                if len(candidates) >= 20:
                    break
        for path in candidates:
            r = rel(path, root)
            items.extend(_parse_fail_lines(read_text(path), source=r))
            if len(items) >= limit:
                break
    items = items[:limit]
    first = items[0] if items else None
    return {
        "ok": len(items) == 0,
        "tool": "summarize_failures",
        "items": items,
        "count": len(items),
        "first_failure": first,
        "summary": (
            f"failures={len(items)}"
            if items
            else "no FAIL lines found"
        ),
        "result": {"failures": items, "first_failure": first},
    }


def handle(tool: str, root: Path, data: dict[str, Any]) -> dict[str, Any]:
    if tool == "detect_build_system":
        return detect_build_system(root, data)
    if tool == "run_validation":
        return run_validation(root, data)
    if tool == "summarize_failures":
        return summarize_failures(root, data)
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
