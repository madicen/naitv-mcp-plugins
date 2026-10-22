#!/usr/bin/env python3
"""environment-validator: parse and compare .env files (JSON I/O, stdlib)."""
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
    "check_env_vars",
    "parse_env_files",
    "compare_env_templates",
    "env_summary",
}
_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


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


def is_env_file(name: str) -> bool:
    if name == ".env" or name == ".env.example":
        return True
    if name.startswith(".env."):
        return True
    if name.endswith(".env"):
        return True
    return False


def is_template_env(name: str) -> bool:
    return name in {".env.example", ".env.sample", ".env.template"} or name.endswith(
        ".env.example"
    )


def parse_env_text(text: str) -> list[tuple[str, str]]:
    """Return (key, value) pairs in file order; keys only from real KEY= lines."""
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = _ENV_LINE.match(line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key not in seen:
            seen.add(key)
            pairs.append((key, val))
    return pairs


def collect_env_files(root: Path, depth: int) -> list[Path]:
    files = [p for p in iter_files(root, depth) if is_env_file(p.name)]
    # Root-level hidden env files (iter_files already includes them as files).
    files.sort(key=lambda p: rel(p, root))
    return files


def file_keys(path: Path) -> list[str]:
    return [k for k, _ in parse_env_text(read_text(path))]


def _required_keys(data: dict[str, Any], templates: list[Path]) -> list[str]:
    raw = data.get("required")
    if isinstance(raw, list):
        return [str(x) for x in raw if isinstance(x, str) and x]
    if isinstance(raw, str) and raw.strip():
        return [p.strip() for p in raw.split(",") if p.strip()]
    keys: list[str] = []
    seen: set[str] = set()
    for t in templates:
        for k in file_keys(t):
            if k not in seen:
                seen.add(k)
                keys.append(k)
    return keys


def parse_env_files(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    path_s = str(data.get("path") or data.get("file") or "").strip()
    limit = max(1, min(int(data.get("limit", 100)), 500))
    if path_s:
        target = root / path_s
        files = [target] if target.is_file() and is_env_file(target.name) else []
    else:
        files = collect_env_files(root, depth)
    file_rows: list[dict[str, Any]] = []
    vars_rows: list[dict[str, str]] = []
    all_keys: list[str] = []
    for f in files:
        keys = file_keys(f)
        r = rel(f, root)
        file_rows.append({"path": r, "keys": keys, "key_count": len(keys)})
        for k in keys:
            vars_rows.append({"path": r, "key": k})
            if k not in all_keys:
                all_keys.append(k)
            if len(vars_rows) >= limit:
                break
        if len(vars_rows) >= limit:
            break
    content = "\n".join(all_keys)
    return {
        "loaded": bool(file_rows),
        "content": content,
        "path": file_rows[0]["path"] if file_rows else path_s,
        "files": file_rows,
        "vars": vars_rows[:limit],
        "count": len(vars_rows[:limit]),
        "tool": "parse_env_files",
    }


def check_env_vars(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    files = collect_env_files(root, depth)
    templates = [p for p in files if is_template_env(p.name)]
    envs = [p for p in files if not is_template_env(p.name)]
    required = _required_keys(data, templates)
    present: set[str] = set()
    key_paths: dict[str, str] = {}
    for p in envs:
        for k in file_keys(p):
            present.add(k)
            key_paths.setdefault(k, rel(p, root))
    for p in templates:
        for k in file_keys(p):
            key_paths.setdefault(k, rel(p, root))
    missing = [k for k in required if k not in present]
    # unused = present in env but not required (only when required non-empty)
    unused = [k for k in sorted(present) if required and k not in set(required)]
    violations: list[dict[str, str]] = []
    for k in missing:
        violations.append(
            {
                "path": key_paths.get(k, templates and rel(templates[0], root) or ""),
                "key": k,
                "rule": "missing",
            }
        )
    for k in unused:
        violations.append(
            {"path": key_paths.get(k, ""), "key": k, "rule": "unused"}
        )
    return {
        "ok": len(missing) == 0,
        "violations": violations,
        "count": len(violations),
        "missing": missing,
        "unused": unused,
        "required": required,
        "tool": "check_env_vars",
    }


def compare_env_templates(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    template_s = str(data.get("template_path") or data.get("path") or "").strip()
    env_s = str(data.get("env_path") or data.get("file") or "").strip()
    files = collect_env_files(root, depth)
    templates = [p for p in files if is_template_env(p.name)]
    envs = [p for p in files if not is_template_env(p.name)]

    def resolve(hint: str, candidates: list[Path], fallback: list[Path]) -> Path | None:
        if hint:
            p = root / hint
            if p.is_file():
                return p
        if candidates:
            return candidates[0]
        if fallback:
            return fallback[0]
        return None

    tpath = resolve(template_s, templates, files)
    epath = resolve(env_s, envs, [p for p in files if p != tpath])
    tkeys = set(file_keys(tpath)) if tpath else set()
    ekeys = set(file_keys(epath)) if epath else set()
    missing = sorted(tkeys - ekeys)
    extra = sorted(ekeys - tkeys)
    return {
        "ok": len(missing) == 0,
        "tool": "compare_env_templates",
        "template_path": rel(tpath, root) if tpath else "",
        "env_path": rel(epath, root) if epath else "",
        "missing": missing,
        "extra": extra,
        "result": {"missing": missing, "extra": extra},
        "count": len(missing) + len(extra),
    }


def env_summary(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    limit = max(1, min(int(data.get("limit", 20)), 100))
    files = collect_env_files(root, depth)
    items: list[dict[str, Any]] = []
    for f in files[:limit]:
        keys = file_keys(f)
        items.append(
            {
                "path": rel(f, root),
                "key_count": len(keys),
                "keys": keys,
                "is_template": is_template_env(f.name),
            }
        )
    return {
        "items": items,
        "count": len(items),
        "truncated": len(files) > limit,
        "file_count": len(files),
        "tool": "env_summary",
    }


def handle(tool: str, root: Path, data: dict[str, Any]) -> dict[str, Any]:
    if tool == "check_env_vars":
        return check_env_vars(root, data)
    if tool == "parse_env_files":
        return parse_env_files(root, data)
    if tool == "compare_env_templates":
        return compare_env_templates(root, data)
    if tool == "env_summary":
        return env_summary(root, data)
    return {"ok": False, "tool": tool, "error": "unknown tool"}


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
