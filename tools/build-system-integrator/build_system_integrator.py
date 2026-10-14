#!/usr/bin/env python3
"""build-system-integrator: detect/list/run/parse local builds (JSON I/O)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 1_000_000
MAX_TAIL_BYTES = 8_192
DEFAULT_SKIP_DIRS = {
    "node_modules",
    ".git",
    "vendor",
    ".venv",
    "dist",
    "build",
    "__pycache__",
}
# Marker files at repo root (and depth 1) → tool id.
ROOT_MARKERS: list[tuple[str, tuple[str, ...]]] = [
    ("make", ("Makefile", "makefile", "GNUmakefile")),
    ("go", ("go.mod",)),
    ("npm", ("package.json",)),
    ("cargo", ("Cargo.toml",)),
    ("python", ("pyproject.toml", "setup.py", "requirements.txt")),
]
GO_TARGETS = ("build", "test", "vet")
CARGO_TARGETS = ("build", "test", "check")
MAKE_TARGET_RE = re.compile(r"^([A-Za-z0-9_.][A-Za-z0-9_.%-]*):")
# file:line:col: msg  or file:line: msg
ERROR_RE = re.compile(
    r"^(?P<file>[^\s:][^:\n]*?):(?P<line>\d+)(?::\d+)?: (?P<message>.+)$"
)


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


def _scan_markers(root: Path) -> list[tuple[str, str]]:
    """Return (tool, relative config path) pairs, deterministic order."""
    found: list[tuple[str, str]] = []
    seen_files: set[str] = set()
    search_dirs = [root]
    try:
        for ent in sorted(os.scandir(root), key=lambda e: e.name):
            if ent.is_dir(follow_symlinks=False) and not ent.name.startswith("."):
                if ent.name in DEFAULT_SKIP_DIRS:
                    continue
                search_dirs.append(Path(ent.path))
    except OSError:
        pass
    for directory in search_dirs:
        for tool, names in ROOT_MARKERS:
            for name in names:
                path = directory / name
                if not path.is_file():
                    continue
                rel = str(path.relative_to(root))
                if rel in seen_files:
                    continue
                seen_files.add(rel)
                found.append((tool, rel))
    return found


def detect_build_tool(root: Path) -> dict[str, Any]:
    pairs = _scan_markers(root)
    if not pairs:
        return {"tool": "unknown", "config_files": []}
    # Prefer root-level markers, then first by marker priority order.
    root_pairs = [p for p in pairs if "/" not in p[1] and "\\" not in p[1]]
    chosen = (root_pairs or pairs)[0]
    tool = chosen[0]
    config_files = sorted({rel for t, rel in pairs if t == tool})
    return {"tool": tool, "config_files": config_files}


def _make_targets(root: Path) -> list[str]:
    for name in ("Makefile", "makefile", "GNUmakefile"):
        path = root / name
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            break
    else:
        return []
    targets: list[str] = []
    for line in text.splitlines():
        if line.startswith("\t") or line.startswith(" ") or line.startswith("#"):
            continue
        m = MAKE_TARGET_RE.match(line)
        if not m:
            continue
        t = m.group(1)
        if t.startswith("."):
            continue
        if t not in targets:
            targets.append(t)
    return targets


def _npm_targets(root: Path) -> list[str]:
    path = root / "package.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict):
        return []
    return sorted(str(k) for k in scripts.keys())


def list_build_targets(root: Path) -> dict[str, Any]:
    detected = detect_build_tool(root)
    tool = detected["tool"]
    if tool == "make":
        targets = _make_targets(root)
    elif tool == "go":
        targets = list(GO_TARGETS)
    elif tool == "npm":
        targets = _npm_targets(root)
    elif tool == "cargo":
        targets = list(CARGO_TARGETS)
    elif tool == "python":
        targets = ["pytest"]
    else:
        targets = []
    return {"tool": tool, "targets": targets}


def _cmd_for_target(tool: str, target: str) -> list[str] | None:
    if tool == "make":
        if not re.fullmatch(r"[A-Za-z0-9_.%-]+", target):
            return None
        return ["make", target]
    if tool == "go":
        mapping = {
            "build": ["go", "build", "./..."],
            "test": ["go", "test", "./..."],
            "vet": ["go", "vet", "./..."],
        }
        return mapping.get(target)
    if tool == "npm":
        if not re.fullmatch(r"[A-Za-z0-9_.:@/-]+", target):
            return None
        return ["npm", "run", target, "--if-present"]
    if tool == "cargo":
        mapping = {
            "build": ["cargo", "build"],
            "test": ["cargo", "test"],
            "check": ["cargo", "check"],
        }
        return mapping.get(target)
    if tool == "python" and target == "pytest":
        return ["python3", "-m", "pytest", "-q"]
    return None


def run_build_target(root: Path, target: str, *, timeout: float = 4.0) -> dict[str, Any]:
    detected = detect_build_tool(root)
    tool = detected["tool"]
    if tool == "unknown":
        return {
            "exit_code": 2,
            "output_tail": "no build tool detected",
            "tool": tool,
            "target": target,
        }
    cmd = _cmd_for_target(tool, target)
    if cmd is None:
        return {
            "exit_code": 2,
            "output_tail": f"unsupported target for {tool}: {target}",
            "tool": tool,
            "target": target,
        }
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return {
            "exit_code": 127,
            "output_tail": f"command not found: {exc.filename or cmd[0]}",
            "tool": tool,
            "target": target,
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": 124,
            "output_tail": f"timed out after {timeout}s",
            "tool": tool,
            "target": target,
        }
    blob = (proc.stdout or b"") + (proc.stderr or b"")
    if len(blob) > MAX_TAIL_BYTES:
        blob = blob[-MAX_TAIL_BYTES:]
    text = blob.decode("utf-8", errors="replace")
    return {
        "exit_code": int(proc.returncode),
        "output_tail": text,
        "tool": tool,
        "target": target,
    }


def parse_build_errors(output: str) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for line in output.splitlines():
        m = ERROR_RE.match(line.strip())
        if not m:
            continue
        file_ = m.group("file")
        line_no = int(m.group("line"))
        message = m.group("message").strip()
        key = (file_, line_no, message)
        if key in seen:
            continue
        seen.add(key)
        errors.append({"file": file_, "line": line_no, "message": message})
    errors.sort(key=lambda e: (e["file"], e["line"], e["message"]))
    return {"errors": errors, "count": len(errors)}


def main() -> None:
    tool = os.environ.get("TOOL_NAME", "").strip()
    handlers = {
        "detect_build_tool",
        "list_build_targets",
        "run_build_target",
        "parse_build_errors",
    }
    if tool not in handlers:
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

    if tool == "parse_build_errors":
        output = data.get("output")
        if not isinstance(output, str):
            _error("output required")
        result = parse_build_errors(output)
    else:
        root_raw = data.get("root_path")
        if not root_raw:
            _error("root_path required")
        if not isinstance(root_raw, str):
            _error("root_path must be a string")
        root = validate_root_path(root_raw)
        if tool == "detect_build_tool":
            result = detect_build_tool(root)
        elif tool == "list_build_targets":
            result = list_build_targets(root)
        else:
            target = data.get("target")
            if not isinstance(target, str) or not target.strip():
                _error("target required")
            result = run_build_target(root, target.strip())

    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
