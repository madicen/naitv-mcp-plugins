#!/usr/bin/env python3
"""mistake-tracker: record/search recurring mistakes (SQLite under ~/.cache)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 1_000_000
MAX_DESC = 2_000
MAX_FILE = 512
MAX_CATEGORY = 64
MAX_RESULTS = 100
_CAT_RE = re.compile(r"^[A-Za-z0-9_./-]{1,64}$")


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


def cache_dir() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    path = base / "naitv-mcp" / "mistake-tracker"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path_for(root: Path) -> Path:
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]
    return cache_dir() / f"{digest}.sqlite"


def connect(root: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path_for(root)), timeout=5)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mistakes (
          id TEXT PRIMARY KEY,
          description TEXT NOT NULL,
          category TEXT NOT NULL,
          file TEXT NOT NULL,
          fingerprint TEXT NOT NULL,
          recorded_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mistakes_fp ON mistakes(fingerprint)"
    )
    conn.commit()
    return conn


def _fingerprint(description: str, category: str) -> str:
    norm = re.sub(r"\s+", " ", description.strip().lower())
    return hashlib.sha256(f"{category}|{norm}".encode()).hexdigest()[:16]


def _make_id(description: str, category: str, file: str, recorded_at: float) -> str:
    # Deterministic for identical inputs (golden-friendly).
    bucket = int(recorded_at)
    raw = f"{category}|{file}|{description}|{bucket}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def record_mistake(
    root: Path,
    description: str,
    category: str,
    file: str,
    *,
    recorded_at: float | None = None,
) -> dict[str, Any]:
    if not isinstance(description, str) or not description.strip():
        _error("description required")
    desc = description.strip()
    if len(desc) > MAX_DESC:
        _error(f"description exceeds {MAX_DESC} chars")
    if not isinstance(category, str) or not _CAT_RE.match(category):
        _error("category must match [A-Za-z0-9_./-]{1,64}")
    if not isinstance(file, str) or not file.strip():
        _error("file required")
    file_s = file.strip().replace("\\", "/")
    if len(file_s) > MAX_FILE or ".." in file_s.split("/"):
        _error("file path invalid")
    now = time.time() if recorded_at is None else float(recorded_at)
    mid = _make_id(desc, category, file_s, now)
    fp = _fingerprint(desc, category)
    conn = connect(root)
    try:
        conn.execute(
            """
            INSERT INTO mistakes(id, description, category, file, fingerprint, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              description=excluded.description,
              category=excluded.category,
              file=excluded.file,
              fingerprint=excluded.fingerprint,
              recorded_at=excluded.recorded_at
            """,
            (mid, desc, category, file_s, fp, now),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": mid, "stored": True, "category": category, "file": file_s}


def search_mistakes(
    root: Path,
    query: str,
    *,
    category: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    if not isinstance(query, str) or not query.strip():
        _error("query required")
    q = query.strip().lower()
    limit = max(1, min(int(limit), MAX_RESULTS))
    if category is not None and category != "":
        if not isinstance(category, str) or not _CAT_RE.match(category):
            _error("category must match [A-Za-z0-9_./-]{1,64}")
    conn = connect(root)
    try:
        rows = conn.execute(
            "SELECT id, description, category, file, recorded_at FROM mistakes"
        ).fetchall()
    finally:
        conn.close()
    matches: list[dict[str, Any]] = []
    for mid, desc, cat, file_s, _ts in rows:
        if category and cat != category:
            continue
        text = f"{desc} {file_s} {cat}".lower()
        if q not in text:
            continue
        # simple score: query length / text length, prefer earlier match
        score = min(1.0, len(q) / max(len(text), 1))
        if text.startswith(q):
            score = min(1.0, score + 0.2)
        matches.append(
            {
                "id": mid,
                "description": desc,
                "category": cat,
                "file": file_s,
                "score": round(score, 6),
            }
        )
    matches.sort(key=lambda m: (-m["score"], m["id"]))
    matches = matches[:limit]
    return {
        "matches": matches,
        "count": len(matches),
        "scores": [m["score"] for m in matches],
    }


def list_recurring_mistakes(root: Path, *, min_count: int = 2) -> dict[str, Any]:
    min_count = max(1, min(int(min_count), 1000))
    conn = connect(root)
    try:
        rows = conn.execute(
            "SELECT fingerprint, description, category, COUNT(*) FROM mistakes "
            "GROUP BY fingerprint ORDER BY COUNT(*) DESC, fingerprint ASC"
        ).fetchall()
    finally:
        conn.close()
    recurring = []
    counts = []
    for fp, desc, cat, cnt in rows:
        if int(cnt) < min_count:
            continue
        recurring.append(
            {
                "fingerprint": fp,
                "description": desc,
                "category": cat,
                "count": int(cnt),
            }
        )
        counts.append(int(cnt))
    return {"recurring": recurring, "counts": counts, "count": len(recurring)}


def mistake_stats(root: Path, *, since: float | str | None = None) -> dict[str, Any]:
    since_ts: float | None = None
    if since is not None and since != "":
        if isinstance(since, (int, float)):
            since_ts = float(since)
        elif isinstance(since, str):
            try:
                since_ts = float(since)
            except ValueError:
                _error("since must be a unix timestamp number")
        else:
            _error("since must be a unix timestamp number")
    conn = connect(root)
    try:
        if since_ts is None:
            rows = conn.execute(
                "SELECT category FROM mistakes"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT category FROM mistakes WHERE recorded_at >= ?",
                (since_ts,),
            ).fetchall()
    finally:
        conn.close()
    cats = Counter(r[0] for r in rows)
    by_category = [
        {"category": c, "count": n} for c, n in sorted(cats.items(), key=lambda x: (-x[1], x[0]))
    ]
    return {"total": len(rows), "by_category": by_category}


def main() -> None:
    tool = os.environ.get("TOOL_NAME", "").strip()
    if tool not in (
        "record_mistake",
        "search_mistakes",
        "list_recurring_mistakes",
        "mistake_stats",
    ):
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

    # Deterministic clock for golden: optional recorded_at; else time.time()
    if tool == "record_mistake":
        desc = data.get("description")
        cat = data.get("category")
        file_s = data.get("file")
        if not isinstance(desc, str):
            _error("description required")
        if not isinstance(cat, str):
            _error("category required")
        if not isinstance(file_s, str):
            _error("file required")
        ra = data.get("recorded_at")
        result = record_mistake(
            root, desc, cat, file_s, recorded_at=float(ra) if ra is not None else None
        )
    elif tool == "search_mistakes":
        q = data.get("query")
        if not isinstance(q, str):
            _error("query required")
        result = search_mistakes(
            root,
            q,
            category=data.get("category"),
            limit=int(data.get("limit", 20)),
        )
    elif tool == "list_recurring_mistakes":
        result = list_recurring_mistakes(
            root, min_count=int(data.get("min_count", 2))
        )
    else:
        result = mistake_stats(root, since=data.get("since"))

    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
