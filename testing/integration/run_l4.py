#!/usr/bin/env python3
"""L4: drive structural-anchor tools through a real naitv-mcp serve (stdio MCP)."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "testing" / "fixtures"


class MCPClient:
    def __init__(self, proc: subprocess.Popen[bytes]) -> None:
        self.proc = proc
        self._id = 0

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            msg["params"] = params
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write((json.dumps(msg) + "\n").encode())
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            err = self.proc.stderr.read().decode() if self.proc.stderr else ""
            raise RuntimeError(f"MCP server closed stdout; stderr={err[:500]}")
        data = json.loads(line.decode())
        if "error" in data:
            raise RuntimeError(f"MCP error for {method}: {data['error']}")
        return data.get("result")

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        assert self.proc.stdin
        self.proc.stdin.write((json.dumps(msg) + "\n").encode())
        self.proc.stdin.flush()


def ulidish(n: int) -> str:
    return f"01L4TEST{n:016d}"


def build_seed(plugin: str, home: Path, *, include_slow: bool) -> Path:
    manifest = json.loads(
        (REPO_ROOT / "plugins" / plugin / "plugin.json").read_text(encoding="utf-8")
    )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entries: list[dict[str, Any]] = []
    i = 1
    for raw in manifest.get("entries", []):
        if raw.get("kind") != "tool":
            continue
        entries.append(
            {
                "id": ulidish(i),
                "kind": "tool",
                "name": raw["name"],
                "group": "",
                "body": raw.get("body", ""),
                "tags": raw.get("tags") or [],
                "fields": raw.get("fields") or {},
                "status": "active",
                "delivery": raw.get("delivery") or "on-demand",
                "proposed_by": "l4",
                "proposed_at": None,
                "target_id": "",
                "created_at": now,
                "updated_at": now,
            }
        )
        i += 1
    if include_slow:
        entries.append(
            {
                "id": ulidish(i),
                "kind": "tool",
                "name": "slow_sleep",
                "group": "",
                "body": "Sleep longer than timeout (L4 probe)",
                "tags": [],
                "fields": {
                    "exec": "sleep 5",
                    "io_mode": "json",
                    "timeout": "500ms",
                },
                "status": "active",
                "delivery": "on-demand",
                "proposed_by": "l4",
                "proposed_at": None,
                "target_id": "",
                "created_at": now,
                "updated_at": now,
            }
        )
    seed = home / "seed.json"
    seed.write_text(
        json.dumps({"schema_version": 1, "exported_at": now, "entries": entries}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return seed


def prepare_home(plugin: str, home: Path) -> None:
    src = REPO_ROOT / "tools" / plugin
    dest_parent = home / ".config" / "naitv-mcp" / "tools"
    dest_parent.mkdir(parents=True, exist_ok=True)
    dest = dest_parent / plugin
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    dest.symlink_to(src, target_is_directory=True)


def start_server(db: Path, home: Path) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["XDG_CACHE_HOME"] = str(home / ".cache")
    env["NAITV_MCP_DB"] = str(db)
    return subprocess.Popen(
        ["naitv-mcp", "serve", "--db", str(db)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


def tool_text(result: dict[str, Any]) -> tuple[str, bool]:
    is_error = bool(result.get("isError"))
    content = result.get("content") or []
    if not content:
        return "", is_error
    first = content[0]
    return str(first.get("text", "")), is_error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plugin", nargs="?", default="structural-anchor")
    args = parser.parse_args()

    if shutil.which("naitv-mcp") is None:
        print("FAIL: naitv-mcp binary not on PATH", file=sys.stderr)
        return 2

    failures = 0
    with tempfile.TemporaryDirectory(prefix="naitv-l4-") as tmp:
        home = Path(tmp)
        db = home / "l4.db"
        prepare_home(args.plugin, home)
        seed = build_seed(args.plugin, home, include_slow=True)
        imp = subprocess.run(
            ["naitv-mcp", "import", str(seed), "--db", str(db), "--replace"],
            capture_output=True,
            text=True,
            check=False,
        )
        if imp.returncode != 0:
            print(f"FAIL import: {imp.stderr}", file=sys.stderr)
            return 1

        proc = start_server(db, home)
        try:
            client = MCPClient(proc)
            client.request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "l4-harness", "version": "0"},
                },
            )
            client.notify("notifications/initialized")

            listed = client.request("tools/list")
            names = {t["name"] for t in listed.get("tools", [])}
            for want in (
                "get_project_map",
                "list_languages",
                "get_codebase_statistics",
                "slow_sleep",
            ):
                if want not in names:
                    print(f"FAIL tools/list missing {want}: {sorted(names)}")
                    failures += 1
                else:
                    print(f"PASS tools/list has {want}")

            for tool in listed.get("tools", []):
                if tool["name"] in {
                    "get_project_map",
                    "list_languages",
                    "get_codebase_statistics",
                }:
                    if not (tool.get("description") or "").strip():
                        print(f"FAIL {tool['name']}: empty description")
                        failures += 1
                    if tool.get("inputSchema") is None:
                        print(f"FAIL {tool['name']}: missing inputSchema")
                        failures += 1

            fixture = str(FIXTURES / "py-small")
            for name in (
                "get_project_map",
                "list_languages",
                "get_codebase_statistics",
            ):
                result = client.request(
                    "tools/call",
                    {
                        "name": name,
                        "arguments": {"root_path": fixture, "depth": 3},
                    },
                )
                text, is_err = tool_text(result)
                if is_err:
                    print(f"FAIL {name} happy path error: {text[:300]}")
                    failures += 1
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError as exc:
                    print(f"FAIL {name} not JSON: {exc} ({text[:200]})")
                    failures += 1
                    continue
                ok = True
                if name == "get_project_map" and "packages" not in payload:
                    ok = False
                if name == "list_languages" and "languages" not in payload:
                    ok = False
                if name == "get_codebase_statistics" and "total_files" not in payload:
                    ok = False
                if ok:
                    print(f"PASS {name} happy path")
                else:
                    print(f"FAIL {name} shape: {payload}")
                    failures += 1

            # Invalid input → structured error, not a crash
            result = client.request(
                "tools/call",
                {"name": "get_project_map", "arguments": {"depth": 1}},
            )
            text, is_err = tool_text(result)
            if not is_err:
                print(f"FAIL invalid input should error: {text[:200]}")
                failures += 1
            else:
                try:
                    err_obj = json.loads(text)
                except json.JSONDecodeError:
                    print(f"FAIL invalid input error not JSON: {text[:200]}")
                    failures += 1
                else:
                    if err_obj.get("ok") is False:
                        print("PASS invalid input structured error")
                    else:
                        print(f"FAIL error payload missing ok:false: {err_obj}")
                        failures += 1

            # Timeout then prove server still responds
            t0 = time.perf_counter()
            result = client.request("tools/call", {"name": "slow_sleep", "arguments": {}})
            elapsed = time.perf_counter() - t0
            text, is_err = tool_text(result)
            if not is_err:
                print(f"FAIL slow_sleep should time out: {text[:200]}")
                failures += 1
            elif elapsed > 4.0:
                print(f"FAIL timeout took too long ({elapsed:.2f}s)")
                failures += 1
            else:
                print(f"PASS timeout reported ({elapsed:.2f}s)")

            result = client.request(
                "tools/call",
                {
                    "name": "list_languages",
                    "arguments": {
                        "root_path": str(FIXTURES / "empty"),
                        "depth": 1,
                    },
                },
            )
            text, is_err = tool_text(result)
            if is_err:
                print(f"FAIL server unresponsive after timeout: {text[:200]}")
                failures += 1
            else:
                print("PASS server responsive after timeout")
        finally:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.terminate()

    print(f"\nSummary: failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
