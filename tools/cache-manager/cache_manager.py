#!/usr/bin/env python3
"""cache-manager: namespaced key/value cache (SQLite under ~/.cache)."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 1_000_000
MAX_KEY_LEN = 256
MAX_NS_LEN = 64
MAX_VALUE_BYTES = 256_000
DEFAULT_TTL = 3600
_NS_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,64}$")
_KEY_RE = re.compile(r"^[A-Za-z0-9_./:@-]{1,256}$")


def _error(message: str, *, code: int = 1) -> None:
    print(message, file=sys.stderr)
    sys.exit(code)


def cache_dir() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        base = Path(xdg)
    else:
        base = Path.home() / ".cache"
    path = base / "naitv-mcp" / "cache-manager"
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_namespace(ns: str | None) -> str:
    if ns is None or ns == "":
        return "default"
    if not isinstance(ns, str) or not _NS_RE.match(ns):
        _error("namespace must match [A-Za-z0-9_.:@-]{1,64}")
    return ns


def validate_key(key: Any) -> str:
    if not isinstance(key, str) or not key or not _KEY_RE.match(key):
        _error("key must match [A-Za-z0-9_./:@-]{1,256}")
    if ".." in key.split("/"):
        _error("key must not contain '..'")
    return key


def connect(namespace: str) -> sqlite3.Connection:
    db = cache_dir() / f"{namespace}.sqlite"
    conn = sqlite3.connect(str(db), timeout=5)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL,
          size_bytes INTEGER NOT NULL,
          expires_at REAL,
          created_at REAL NOT NULL,
          accessed_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
          name TEXT PRIMARY KEY,
          value REAL NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO meta(name, value) VALUES ('hits', 0), ('misses', 0)"
    )
    conn.commit()
    return conn


def _bump(conn: sqlite3.Connection, name: str, delta: float = 1.0) -> None:
    conn.execute("UPDATE meta SET value = value + ? WHERE name = ?", (delta, name))


def _meta(conn: sqlite3.Connection, name: str) -> float:
    row = conn.execute("SELECT value FROM meta WHERE name = ?", (name,)).fetchone()
    return float(row[0]) if row else 0.0


def _purge_expired(conn: sqlite3.Connection, now: float) -> int:
    cur = conn.execute(
        "DELETE FROM entries WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,)
    )
    return int(cur.rowcount or 0)


def cache_get(key: str, *, namespace: str = "default") -> dict[str, Any]:
    ns = validate_namespace(namespace)
    k = validate_key(key)
    now = time.time()
    conn = connect(ns)
    try:
        _purge_expired(conn, now)
        row = conn.execute(
            "SELECT value, expires_at FROM entries WHERE key = ?", (k,)
        ).fetchone()
        if not row:
            _bump(conn, "misses")
            conn.commit()
            return {"hit": False, "key": k, "namespace": ns, "value": None}
        value_s, expires_at = row
        if expires_at is not None and float(expires_at) <= now:
            conn.execute("DELETE FROM entries WHERE key = ?", (k,))
            _bump(conn, "misses")
            conn.commit()
            return {"hit": False, "key": k, "namespace": ns, "value": None}
        conn.execute(
            "UPDATE entries SET accessed_at = ? WHERE key = ?", (now, k)
        )
        _bump(conn, "hits")
        conn.commit()
        try:
            value = json.loads(value_s)
        except json.JSONDecodeError:
            value = value_s
        return {"hit": True, "key": k, "namespace": ns, "value": value}
    finally:
        conn.close()


def cache_put(
    key: str,
    value: Any,
    *,
    namespace: str = "default",
    ttl: int | float | None = DEFAULT_TTL,
) -> dict[str, Any]:
    ns = validate_namespace(namespace)
    k = validate_key(key)
    if ttl is None:
        ttl_i = DEFAULT_TTL
    else:
        try:
            ttl_i = int(ttl)
        except (TypeError, ValueError):
            _error("ttl must be an integer number of seconds")
        if ttl_i < 0:
            _error("ttl must be >= 0 (0 means no expiry)")
    try:
        value_s = json.dumps(value, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as exc:
        _error(f"value not JSON-serializable: {exc}")
    size = len(value_s.encode("utf-8"))
    if size > MAX_VALUE_BYTES:
        _error(f"value exceeds {MAX_VALUE_BYTES} bytes")
    now = time.time()
    expires = None if ttl_i == 0 else now + ttl_i
    conn = connect(ns)
    try:
        _purge_expired(conn, now)
        conn.execute(
            """
            INSERT INTO entries(key, value, size_bytes, expires_at, created_at, accessed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
              value=excluded.value,
              size_bytes=excluded.size_bytes,
              expires_at=excluded.expires_at,
              accessed_at=excluded.accessed_at
            """,
            (k, value_s, size, expires, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "stored": True,
        "key": k,
        "namespace": ns,
        "size_bytes": size,
        "ttl": ttl_i,
    }


def cache_stats(*, namespace: str = "default") -> dict[str, Any]:
    ns = validate_namespace(namespace)
    now = time.time()
    conn = connect(ns)
    try:
        _purge_expired(conn, now)
        rows = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(size_bytes), 0) FROM entries"
        ).fetchone()
        entries = int(rows[0] or 0)
        bytes_ = int(rows[1] or 0)
        hits = _meta(conn, "hits")
        misses = _meta(conn, "misses")
        total = hits + misses
        hit_rate = (hits / total) if total > 0 else 0.0
        conn.commit()
    finally:
        conn.close()
    return {
        "namespace": ns,
        "entries": entries,
        "bytes": bytes_,
        "hit_rate": round(hit_rate, 6),
        "hits": int(hits),
        "misses": int(misses),
    }


def cache_prune(
    *, namespace: str = "default", max_bytes: int | None = None
) -> dict[str, Any]:
    ns = validate_namespace(namespace)
    if max_bytes is None:
        max_b = 0
    else:
        try:
            max_b = int(max_bytes)
        except (TypeError, ValueError):
            _error("max_bytes must be an integer")
        if max_b < 0:
            _error("max_bytes must be >= 0")
    now = time.time()
    conn = connect(ns)
    try:
        removed = _purge_expired(conn, now)
        if max_b == 0:
            cur = conn.execute("DELETE FROM entries")
            removed += int(cur.rowcount or 0)
        else:
            while True:
                row = conn.execute(
                    "SELECT COALESCE(SUM(size_bytes), 0) FROM entries"
                ).fetchone()
                total = int(row[0] or 0)
                if total <= max_b:
                    break
                victim = conn.execute(
                    "SELECT key FROM entries ORDER BY accessed_at ASC, key ASC LIMIT 1"
                ).fetchone()
                if not victim:
                    break
                conn.execute("DELETE FROM entries WHERE key = ?", (victim[0],))
                removed += 1
        rem_row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(size_bytes), 0) FROM entries"
        ).fetchone()
        remaining = int(rem_row[0] or 0)
        remaining_bytes = int(rem_row[1] or 0)
        conn.commit()
    finally:
        conn.close()
    return {
        "namespace": ns,
        "removed": removed,
        "remaining": remaining,
        "remaining_bytes": remaining_bytes,
    }


def main() -> None:
    tool = os.environ.get("TOOL_NAME", "").strip()
    if tool not in ("cache_get", "cache_put", "cache_stats", "cache_prune"):
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

    ns = data.get("namespace", "default")
    if tool == "cache_get":
        key = data.get("key")
        if not isinstance(key, str) or not key:
            _error("key required")
        result = cache_get(key, namespace=ns if isinstance(ns, str) else "default")
    elif tool == "cache_put":
        key = data.get("key")
        if not isinstance(key, str) or not key:
            _error("key required")
        if "value" not in data:
            _error("value required")
        result = cache_put(
            key,
            data["value"],
            namespace=ns if isinstance(ns, str) else "default",
            ttl=data.get("ttl", DEFAULT_TTL),
        )
    elif tool == "cache_stats":
        result = cache_stats(namespace=ns if isinstance(ns, str) else "default")
    else:
        result = cache_prune(
            namespace=ns if isinstance(ns, str) else "default",
            max_bytes=data.get("max_bytes", 0),
        )

    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
