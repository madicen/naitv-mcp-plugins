#!/usr/bin/env python3
"""logging-enforcer: find log/print calls via regex (grounded)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_LIB = Path(__file__).resolve().parents[1] / "_lib"
if _LIB.is_dir() and str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
import scanutil as su  # noqa: E402

MAX_INPUT_BYTES = 1_000_000
TOOLS = {
    "find_log_calls",
    "check_log_levels",
    "check_sensitive_fields",
    "logging_summary",
}


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

    if tool in ("find_log_calls", "logging_summary"):
        items: list[dict[str, Any]] = []
        for f in files:
            if f.suffix not in {".py", ".go"}:
                continue
            r = su.rel(f, root)
            text = su.read_text(f)
            spans = su.find_log_spans(text)
            if query and not su.match_query(query, r, text):
                continue
            if spans:
                items.append(
                    {
                        "path": r,
                        "score": 1.0,
                        "calls": [{"line": ln, "snippet": sn} for ln, sn in spans[:10]],
                    }
                )
            elif query:
                items.append({"path": r, "score": 0.5})
            if len(items) >= limit:
                break
        return {"items": items, "count": len(items), "truncated": truncated, "tool": tool}

    if tool == "check_log_levels":
        violations: list[dict[str, Any]] = []
        for f in files:
            r = su.rel(f, root)
            text = su.read_text(f)
            if query and not su.match_query(query, r, text):
                continue
            for line, snip in su.find_log_spans(text):
                low = snip.lower()
                if "print(" in low or "fmt.print" in low:
                    violations.append(
                        {"path": r, "line": line, "rule": "print_as_log", "message": snip}
                    )
                if len(violations) >= limit:
                    break
            if len(violations) >= limit:
                break
        return {
            "ok": len(violations) == 0,
            "violations": violations,
            "count": len(violations),
            "tool": tool,
        }

    if tool == "check_sensitive_fields":
        violations = []
        target = root / path_s
        scan = [target] if target.is_file() else files
        for f in scan:
            if not f.is_file():
                continue
            r = su.rel(f, root)
            text = su.read_text(f)
            for line, snip in su.find_log_spans(text):
                for _, key in su.find_secretish(snip):
                    violations.append(
                        {
                            "path": r,
                            "line": line,
                            "rule": "sensitive_in_log",
                            "message": key,
                        }
                    )
            if len(violations) >= limit:
                break
        return {
            "ok": len(violations) == 0,
            "violations": violations[:limit],
            "count": len(violations[:limit]),
            "tool": tool,
        }

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
