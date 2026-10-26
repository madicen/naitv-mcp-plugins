#!/usr/bin/env python3
"""decision-log-runner: parse ADR/decision markdown (JSON I/O, stdlib)."""
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
    "parse_decision_log",
    "search_decisions",
    "check_decision_conflicts",
    "summarize_decisions",
}
_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
_STATUS = re.compile(
    r"(?i)^\s*(?:[-*]\s*)?(?:status|state)\s*[:\|]\s*(.+?)\s*$"
)
_STATUS_INLINE = re.compile(r"(?i)\bstatus\s*:\s*([A-Za-z_-]+)")
_ADR_ID = re.compile(r"(?i)\b(?:ADR[-_ ]?)?(\d{3,5})\b")
_CONTRADICT = {
    frozenset({"accepted", "rejected"}),
    frozenset({"accepted", "deprecated"}),
    frozenset({"proposed", "rejected"}),
    frozenset({"approved", "rejected"}),
    frozenset({"active", "superseded"}),
}


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


def is_decision_file(rpath: str) -> bool:
    parts = rpath.replace("\\", "/").split("/")
    name = parts[-1] if parts else rpath
    lower = name.lower()
    parents = [p.lower() for p in parts[:-1]]
    if lower == "decisions.md":
        return True
    if "decisions" in parents and lower.endswith(".md"):
        return True
    if lower.startswith("adr") and lower.endswith(".md"):
        return True
    # docs/adr/**/*.md or **/adr*/**/*.md
    if lower.endswith(".md") and any(p == "adr" or p.startswith("adr") for p in parents):
        return True
    return False


def _clean_title(raw: str) -> str:
    t = raw.strip()
    t = re.sub(r"^ADR[-_ ]?\d+[:.\s-]*", "", t, flags=re.I).strip()
    t = re.sub(r"^Decision[:.\s-]*", "", t, flags=re.I).strip()
    return t or raw.strip()


def _norm_status(raw: str) -> str:
    s = raw.strip().strip("*_`").split()[0].lower() if raw.strip() else ""
    s = re.sub(r"[^a-z_-]", "", s)
    return s


def _id_for(path: str, title: str, index: int) -> str:
    stem = Path(path).stem
    m = _ADR_ID.search(stem) or _ADR_ID.search(title)
    if m:
        return m.group(1)
    # Prefer filename stem (exists on disk) over invented CamelCase.
    return stem or f"decision-{index}"


def parse_file_decisions(path: Path, root: Path) -> list[dict[str, str]]:
    rpath = rel(path, root)
    text = read_text(path)
    decisions: list[dict[str, str]] = []
    pending_title: str | None = None
    pending_status = ""
    file_status = ""

    def flush() -> None:
        nonlocal pending_title, pending_status
        if not pending_title:
            return
        status = pending_status or file_status or "unknown"
        idx = len(decisions)
        decisions.append(
            {
                "id": _id_for(rpath, pending_title, idx),
                "title": pending_title,
                "status": status,
                "path": rpath,
            }
        )
        pending_title = None
        pending_status = ""

    for line in text.splitlines():
        sm = _STATUS.match(line)
        if sm:
            st = _norm_status(sm.group(1))
            if pending_title:
                pending_status = st
            else:
                file_status = st
            continue
        hm = _HEADING.match(line)
        if hm:
            flush()
            pending_title = _clean_title(hm.group(2))
            inline = _STATUS_INLINE.search(hm.group(2))
            if inline:
                pending_status = _norm_status(inline.group(1))
            continue
    flush()
    # File with status but no heading: use stem as title (real path-derived).
    if not decisions and (file_status or text.strip()):
        stem = Path(rpath).stem
        if stem:
            decisions.append(
                {
                    "id": _id_for(rpath, stem, 0),
                    "title": stem.replace("-", " ").replace("_", " "),
                    "status": file_status or "unknown",
                    "path": rpath,
                }
            )
    return decisions


def collect_decisions(root: Path, depth: int, path_hint: str = "") -> list[dict[str, str]]:
    if path_hint:
        target = root / path_hint
        if target.is_file():
            return parse_file_decisions(target, root)
        if target.is_dir():
            files = [
                p
                for p in iter_files(target, depth)
                if is_decision_file(rel(p, root))
            ]
        else:
            files = []
    else:
        files = [p for p in iter_files(root, depth) if is_decision_file(rel(p, root))]
    files.sort(key=lambda p: rel(p, root))
    out: list[dict[str, str]] = []
    for f in files:
        out.extend(parse_file_decisions(f, root))
    return out


def parse_decision_log(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    path_s = str(data.get("path") or data.get("file") or data.get("log_path") or "").strip()
    decisions = collect_decisions(root, depth, path_s)
    # content: deterministic key listing (ids + titles from files only)
    lines = [f"{d['id']}\t{d['title']}\t{d['status']}\t{d['path']}" for d in decisions]
    return {
        "loaded": bool(decisions),
        "content": "\n".join(lines),
        "path": path_s or (decisions[0]["path"] if decisions else ""),
        "decisions": decisions,
        "count": len(decisions),
        "tool": "parse_decision_log",
    }


def search_decisions(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    query = str(data.get("query") or data.get("pattern") or data.get("text") or "").strip()
    path_s = str(data.get("path") or data.get("file") or data.get("log_path") or "").strip()
    limit = max(1, min(int(data.get("limit", 20)), 100))
    decisions = collect_decisions(root, depth, path_s)
    q = query.lower()
    items: list[dict[str, Any]] = []
    for d in decisions:
        blob = f"{d['id']} {d['title']} {d['status']} {d['path']}".lower()
        if q and q not in blob:
            continue
        score = 1.0 if not q else round(min(1.0, len(q) / max(len(d["title"]), 1)), 4)
        items.append(
            {
                "path": d["path"],
                "id": d["id"],
                "title": d["title"],
                "status": d["status"],
                "score": score,
            }
        )
        if len(items) >= limit:
            break
    return {
        "items": items,
        "count": len(items),
        "truncated": False,
        "tool": "search_decisions",
    }


def check_decision_conflicts(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    path_s = str(data.get("path") or data.get("file") or data.get("log_path") or "").strip()
    decisions = collect_decisions(root, depth, path_s)
    by_title: dict[str, list[dict[str, str]]] = {}
    for d in decisions:
        key = d["title"].strip().lower()
        by_title.setdefault(key, []).append(d)
    violations: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    related_ids: list[str] = []
    for title_key, group in sorted(by_title.items()):
        if len(group) < 2:
            continue
        # duplicate titles
        ids = [g["id"] for g in group]
        paths = [g["path"] for g in group]
        statuses = {_norm_status(g["status"]) for g in group}
        rule = "duplicate_title"
        for pair in _CONTRADICT:
            if pair.issubset(statuses):
                rule = "contradictory_status"
                break
        if len(statuses) > 1 and rule == "duplicate_title":
            # different statuses for same title → treat as conflict
            rule = "contradictory_status"
        row = {
            "rule": rule,
            "title": group[0]["title"],
            "ids": ids,
            "paths": paths,
            "statuses": sorted(statuses),
        }
        conflicts.append(row)
        violations.append(
            {
                "path": paths[0],
                "rule": rule,
                "message": f"{rule}: {group[0]['title']}",
                "ids": ids,
            }
        )
        related_ids.extend(ids)
    # unique related ids preserving order
    seen: set[str] = set()
    uniq_ids: list[str] = []
    for i in related_ids:
        if i not in seen:
            seen.add(i)
            uniq_ids.append(i)
    return {
        "ok": len(violations) == 0,
        "violations": violations,
        "count": len(violations),
        "conflicts": conflicts,
        "related_ids": uniq_ids,
        "tool": "check_decision_conflicts",
    }


def summarize_decisions(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    query = str(
        data.get("topic") or data.get("query") or data.get("pattern") or ""
    ).strip()
    path_s = str(data.get("path") or data.get("file") or data.get("log_path") or "").strip()
    limit = max(1, min(int(data.get("limit", 20)), 100))
    decisions = collect_decisions(root, depth, path_s)
    q = query.lower()
    filtered = [
        d
        for d in decisions
        if not q
        or q in d["title"].lower()
        or q in d["status"].lower()
        or q in d["path"].lower()
        or q in d["id"].lower()
    ][:limit]
    titles = [d["title"] for d in filtered]
    ids = [d["id"] for d in filtered]
    by_status: dict[str, int] = {}
    for d in filtered:
        by_status[d["status"]] = by_status.get(d["status"], 0) + 1
    # summary uses only real titles (no invented prose names)
    summary = "; ".join(titles) if titles else ""
    return {
        "ok": True,
        "tool": "summarize_decisions",
        "summary": summary,
        "decision_ids": ids,
        "titles": titles,
        "items": [
            {"path": d["path"], "id": d["id"], "title": d["title"], "status": d["status"]}
            for d in filtered
        ],
        "result": {
            "count": len(filtered),
            "by_status": dict(sorted(by_status.items())),
            "titles": titles,
        },
    }


def handle(tool: str, root: Path, data: dict[str, Any]) -> dict[str, Any]:
    if tool == "parse_decision_log":
        return parse_decision_log(root, data)
    if tool == "search_decisions":
        return search_decisions(root, data)
    if tool == "check_decision_conflicts":
        return check_decision_conflicts(root, data)
    if tool == "summarize_decisions":
        return summarize_decisions(root, data)
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
