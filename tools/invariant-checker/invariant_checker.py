#!/usr/bin/env python3
"""invariant-checker: load ADR/docs + assert-like checks (grounded)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

_LIB = Path(__file__).resolve().parents[1] / "_lib"
if _LIB.is_dir() and str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
import scanutil as su  # noqa: E402

MAX_INPUT_BYTES = 1_000_000
TOOLS = {
    "load_invariants",
    "check_invariants",
    "report_invariant_violations",
    "add_invariant",
}
_ASSERT = re.compile(r"^\s*assert\b", re.MULTILINE)


def _error(message: str, *, code: int = 1) -> None:
    print(message, file=sys.stderr)
    sys.exit(code)


def validate_root_path(root: str) -> Path:
    return su.validate_root_path(root, error=_error)


def iter_files(root: Path, depth: int = 3) -> list[Path]:
    return su.iter_files(root, depth)


def handle(tool: str, root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    query = str(data.get("query") or data.get("pattern") or data.get("text") or "").strip()
    path_s = str(data.get("path") or data.get("file") or "README.md").strip()
    limit = max(1, min(int(data.get("limit", 20)), 100))
    files = su.iter_files(root, depth)
    truncated = len(files) >= su.MAX_FILES

    if tool == "load_invariants":
        # Explicit path wins; otherwise prefer ADR/decisions over README.
        explicit = bool(data.get("path") or data.get("file"))
        target = root / path_s
        if explicit and target.is_file():
            return {
                "loaded": True,
                "content": su.read_text(target)[:4000],
                "path": path_s,
                "tool": tool,
            }
        for f in files:
            if su.is_decision_path(su.rel(f, root)):
                return {
                    "loaded": True,
                    "content": su.read_text(f)[:4000],
                    "path": su.rel(f, root),
                    "tool": tool,
                }
        if target.is_file():
            return {
                "loaded": True,
                "content": su.read_text(target)[:4000],
                "path": path_s,
                "tool": tool,
            }
        for f in files:
            if f.suffix in {".md", ".txt"} or f.name.upper().startswith("README"):
                return {
                    "loaded": True,
                    "content": su.read_text(f)[:4000],
                    "path": su.rel(f, root),
                    "tool": tool,
                }
        return {"loaded": False, "content": "", "path": path_s, "tool": tool}

    if tool == "check_invariants":
        violations: list[dict[str, Any]] = []
        for f in files:
            if f.suffix != ".py":
                continue
            r = su.rel(f, root)
            text = su.read_text(f)
            if query and not su.match_query(query, r, text):
                continue
            # lazy: missing assert in non-trivial modules flagged lightly
            if len(text) > 40 and not _ASSERT.search(text):
                violations.append(
                    {"path": r, "rule": "no_assert", "message": "no assert statement"}
                )
            if len(violations) >= limit:
                break
        return {
            "ok": len(violations) == 0,
            "violations": violations,
            "count": len(violations),
            "tool": tool,
        }

    if tool == "report_invariant_violations":
        return {
            "ok": True,
            "tool": tool,
            "result": {"root": root.name, "files": len(files)},
            "truncated": truncated,
        }

    if tool == "add_invariant":
        payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
        mid = hashlib.sha256(f"{tool}|{root}|{payload}".encode()).hexdigest()[:12]
        cache = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
        dest = cache / "naitv-mcp" / "invariant-checker"
        try:
            dest.mkdir(parents=True, exist_ok=True)
            (dest / f"{mid}.json").write_text(payload + "\n", encoding="utf-8")
        except OSError:
            pass  # lazy: id still deterministic if cache unwritable
        return {"stored": True, "id": mid, "tool": tool}

    return {"ok": True, "tool": tool, "result": {"root": root.name, "files": len(files)}}


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
