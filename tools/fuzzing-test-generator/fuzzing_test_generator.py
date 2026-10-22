#!/usr/bin/env python3
"""fuzzing-test-generator: discover fuzz targets (JSON I/O, stdlib, dry-run)."""
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
    "find_fuzz_targets",
    "generate_fuzz_target",
    "validate_fuzz_target",
    "run_fuzz_smoke",
}
_GO_FUZZ = re.compile(r"^func\s+(Fuzz[A-Za-z0-9_]+)\s*\(", re.MULTILINE)
_GO_FUNC = re.compile(r"^func\s+(?:\([^)]+\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.MULTILINE)
_PY_DEF = re.compile(r"^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.MULTILINE)
_PY_HYPOTHESIS = re.compile(
    r"(@given\b|@settings\b|from\s+hypothesis\b|import\s+hypothesis\b|atheris\.|import\s+atheris\b)"
)
_IDENT = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")


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


def discover_fuzz_targets(root: Path, depth: int) -> list[dict[str, str]]:
    """Return path+name for Go Fuzz* and Python hypothesis/atheris markers."""
    items: list[dict[str, str]] = []
    for f in iter_files(root, depth):
        r = rel(f, root)
        if f.suffix == ".go":
            text = read_text(f)
            for m in _GO_FUZZ.finditer(text):
                items.append({"path": r, "name": m.group(1), "kind": "go_fuzz"})
        elif f.suffix == ".py":
            text = read_text(f)
            if not _PY_HYPOTHESIS.search(text):
                # also treat def fuzz_* / test_fuzz_* as markers
                defs = _PY_DEF.findall(text)
                fuzz_defs = [d for d in defs if d.startswith("fuzz_") or d.startswith("test_fuzz")]
                for name in fuzz_defs:
                    items.append({"path": r, "name": name, "kind": "python_fuzz"})
                continue
            for name in _PY_DEF.findall(text):
                if name.startswith("_"):
                    continue
                items.append({"path": r, "name": name, "kind": "python_hypothesis"})
    items.sort(key=lambda x: (x["path"], x["name"]))
    return items


def discover_callables(root: Path, depth: int) -> list[dict[str, str]]:
    """Real function names from .py/.go (for templates)."""
    items: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for f in iter_files(root, depth):
        r = rel(f, root)
        if f.suffix == ".py":
            text = read_text(f)
            for name in _PY_DEF.findall(text):
                if name.startswith("_") and not name.startswith("__"):
                    continue
                key = (r, name)
                if key in seen:
                    continue
                seen.add(key)
                items.append({"path": r, "name": name, "lang": "python"})
        elif f.suffix == ".go":
            text = read_text(f)
            for name in _GO_FUNC.findall(text):
                if name.startswith("Test") or name.startswith("Benchmark") or name.startswith("Fuzz"):
                    continue
                key = (r, name)
                if key in seen:
                    continue
                seen.add(key)
                items.append({"path": r, "name": name, "lang": "go"})
    items.sort(key=lambda x: (x["path"], x["name"]))
    return items


def find_fuzz_targets(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    query = str(data.get("query") or data.get("pattern") or "").strip().lower()
    limit = max(1, min(int(data.get("limit", 20)), 100))
    found = discover_fuzz_targets(root, depth)
    items: list[dict[str, Any]] = []
    for t in found:
        if query and query not in t["name"].lower() and query not in t["path"].lower():
            continue
        items.append({"path": t["path"], "name": t["name"], "kind": t["kind"]})
        if len(items) >= limit:
            break
    return {
        "items": items,
        "count": len(items),
        "truncated": len(found) > limit,
        "tool": "find_fuzz_targets",
    }


def _pick_symbol(root: Path, data: dict[str, Any], callables: list[dict[str, str]]) -> dict[str, str] | None:
    hint = str(
        data.get("symbol") or data.get("query") or data.get("name") or data.get("path") or ""
    ).strip()
    if not callables:
        return None
    if hint:
        hl = hint.lower()
        for c in callables:
            if c["name"].lower() == hl or c["path"].lower() == hl:
                return c
        for c in callables:
            if hl in c["name"].lower() or hl in c["path"].lower():
                return c
        # hint not found — do not invent; fall back to first real callable
    return callables[0]


def generate_fuzz_target(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    callables = discover_callables(root, depth)
    existing = discover_fuzz_targets(root, depth)
    target = _pick_symbol(root, data, callables)
    if not target:
        body = "# no callable symbols discovered in repo\n"
        return {
            "generated": body,
            "ok": False,
            "items": [],
            "path": "",
            "name": "",
            "tool": "generate_fuzz_target",
        }
    name = target["name"]
    path = target["path"]
    lang = target["lang"]
    # Template references ONLY the real symbol name — no invented CamelCase wrappers.
    if lang == "go":
        body = (
            f"# fuzz dry-run template for {name} ({path})\n"
            f"# call only the discovered symbol: {name}\n"
            f"# example: result := {name}(fuzzedInput)\n"
        )
    else:
        body = (
            f"# fuzz dry-run template for {name} ({path})\n"
            f"# call only the discovered symbol: {name}\n"
            f"# example: {name}(fuzzed_input)\n"
        )
    return {
        "generated": body,
        "ok": True,
        "items": [{"path": path, "name": name, "text": body}],
        "path": path,
        "name": name,
        "existing_targets": [{"path": t["path"], "name": t["name"]} for t in existing],
        "tool": "generate_fuzz_target",
    }


def validate_fuzz_target(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    path_s = str(data.get("path") or data.get("file") or "").strip()
    template = str(data.get("template") or data.get("text") or data.get("generated") or "")
    callables = discover_callables(root, depth)
    fuzz = discover_fuzz_targets(root, depth)
    real_names = {c["name"] for c in callables} | {t["name"] for t in fuzz}
    real_paths = {c["path"] for c in callables} | {t["path"] for t in fuzz}

    if not template and path_s:
        target = root / path_s
        if target.is_file():
            template = read_text(target)

    violations: list[dict[str, str]] = []
    mentioned = [m.group(1) for m in _IDENT.finditer(template)]
    # Keep identifiers that look like symbols (skip tiny words)
    skip = {
        "fuzz",
        "dry",
        "run",
        "template",
        "for",
        "call",
        "only",
        "the",
        "discovered",
        "symbol",
        "example",
        "result",
        "fuzzedInput",
        "fuzzed_input",
        "def",
        "func",
        "import",
        "from",
        "no",
        "callable",
        "symbols",
        "in",
        "repo",
    }
    candidates = [n for n in mentioned if n not in skip and len(n) > 1]
    matched = [n for n in candidates if n in real_names]
    # path mentions
    path_hit = any(p in template for p in real_paths) if real_paths else False

    if not real_names:
        violations.append(
            {"path": path_s, "rule": "no_symbols", "message": "no symbols in repo"}
        )
    elif not matched and not path_hit:
        violations.append(
            {
                "path": path_s or "",
                "rule": "missing_real_symbol",
                "message": "template mentions no discovered symbol",
            }
        )
    # flag invented CapWords in template that are not real
    for n in candidates:
        if n in real_names or n in skip:
            continue
        if re.match(r"^[A-Z][a-zA-Z0-9]+$", n) and n not in real_names:
            violations.append(
                {
                    "path": path_s or "",
                    "rule": "unknown_symbol",
                    "message": n,  # report the token; caller decides
                    "name": n,
                }
            )

    return {
        "ok": len(violations) == 0,
        "violations": violations,
        "count": len(violations),
        "matched_symbols": matched,
        "tool": "validate_fuzz_target",
    }


def run_fuzz_smoke(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    limit = max(1, min(int(data.get("limit", 20)), 100))
    found = discover_fuzz_targets(root, depth)
    targets = [{"path": t["path"], "name": t["name"]} for t in found[:limit]]
    # Dry-run only — never execute fuzzers.
    summary = f"dry-run ok; targets={len(targets)}"
    return {
        "ok": True,
        "exit_code": 0,
        "summary": summary,
        "targets": targets,
        "count": len(targets),
        "tool": "run_fuzz_smoke",
    }


def handle(tool: str, root: Path, data: dict[str, Any]) -> dict[str, Any]:
    if tool == "find_fuzz_targets":
        return find_fuzz_targets(root, data)
    if tool == "generate_fuzz_target":
        return generate_fuzz_target(root, data)
    if tool == "validate_fuzz_target":
        return validate_fuzz_target(root, data)
    if tool == "run_fuzz_smoke":
        return run_fuzz_smoke(root, data)
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
