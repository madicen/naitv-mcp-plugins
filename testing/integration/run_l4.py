#!/usr/bin/env python3
"""L4: drive plugin tools through a real naitv-mcp serve (stdio MCP).

Smoke expectations come from plugins/<name>/harness.json → l4.
"""
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
sys.path.insert(0, str(REPO_ROOT / "testing"))

from plugin_harness import load_harness  # noqa: E402


class MCPClient:
    def __init__(self, proc: subprocess.Popen[bytes]) -> None:
        self.proc = proc
        self._id = 0

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._id += 1
        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": self._id, "method": method}
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


def resolve_fixture_args(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in args.items():
        if isinstance(v, str) and v.startswith("FIXTURE:"):
            out[k] = str(FIXTURES / v.split(":", 1)[1])
        else:
            out[k] = v
    return out


def build_seed(plugin: str, home: Path, *, include_slow: bool) -> Path:
    manifest = load_harness(plugin)["manifest"]
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
    if not src.is_dir():
        src = REPO_ROOT / "plugins" / plugin
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
    parser.add_argument("plugin")
    args = parser.parse_args()

    if shutil.which("naitv-mcp") is None:
        print("FAIL: naitv-mcp binary not on PATH", file=sys.stderr)
        return 2

    harness = load_harness(args.plugin)
    if harness["profile"] == "rules_only":
        print("SKIP L4: rules_only profile")
        return 0

    tool_names = harness["tool_names"]
    l4 = harness.get("l4") or {}
    smoke_args = resolve_fixture_args(l4.get("smoke_args") or {})
    expect_keys: dict[str, list[str]] = l4.get("expect_keys") or {}
    invalid_tool = l4.get("invalid_tool")
    invalid_args = l4.get("invalid_args") or {}
    post_tool = l4.get("post_timeout_tool")
    post_args = resolve_fixture_args(l4.get("post_timeout_args") or {})

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
            for want in [*tool_names, "slow_sleep"]:
                if want not in names:
                    print(f"FAIL tools/list missing {want}: {sorted(names)}")
                    failures += 1
                else:
                    print(f"PASS tools/list has {want}")

            for tool in listed.get("tools", []):
                if tool["name"] not in tool_names:
                    continue
                if not (tool.get("description") or "").strip():
                    print(f"FAIL {tool['name']}: empty description")
                    failures += 1
                if tool.get("inputSchema") is None:
                    print(f"FAIL {tool['name']}: missing inputSchema")
                    failures += 1

            if smoke_args:
                for name in tool_names:
                    result = client.request(
                        "tools/call",
                        {"name": name, "arguments": smoke_args},
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
                    keys = expect_keys.get(name) or []
                    missing = [k for k in keys if k not in payload]
                    if missing:
                        print(f"FAIL {name} missing keys {missing}: {payload}")
                        failures += 1
                    else:
                        print(f"PASS {name} happy path")

            if invalid_tool:
                result = client.request(
                    "tools/call",
                    {"name": invalid_tool, "arguments": invalid_args},
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

            if post_tool and post_args:
                result = client.request(
                    "tools/call",
                    {"name": post_tool, "arguments": post_args},
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
