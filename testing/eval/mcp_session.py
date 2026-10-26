"""Shared stdio MCP session helpers for L5 (and reuse of L4 patterns)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "testing"))

from plugin_harness import link_tools_lib, load_harness, load_manifest, tool_names  # noqa: E402


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

    def call_tool(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        is_error = bool(result.get("isError"))
        content = result.get("content") or []
        text = str(content[0].get("text", "")) if content else ""
        return text, is_error


def _ulidish(n: int) -> str:
    return f"01L5EVAL{n:016d}"


def plugin_tool_names(plugins: list[str]) -> frozenset[str]:
    names: set[str] = set()
    for plugin in plugins:
        try:
            h = load_harness(plugin)
        except FileNotFoundError:
            continue
        configured = (h.get("l5") or {}).get("tool_names")
        if configured:
            names.update(configured)
        else:
            names.update(h["tool_names"])
    return frozenset(names)


def build_plugin_seed(plugins: list[str], path: Path) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entries: list[dict[str, Any]] = []
    i = 1
    for plugin in plugins:
        manifest = load_manifest(plugin)
        for raw in manifest.get("entries", []):
            if raw.get("kind") != "tool":
                continue
            entries.append(
                {
                    "id": _ulidish(i),
                    "kind": "tool",
                    "name": raw["name"],
                    "group": "",
                    "body": raw.get("body", ""),
                    "tags": raw.get("tags") or [],
                    "fields": raw.get("fields") or {},
                    "status": "active",
                    "delivery": raw.get("delivery") or "on-demand",
                    "proposed_by": "l5",
                    "proposed_at": None,
                    "target_id": "",
                    "created_at": now,
                    "updated_at": now,
                }
            )
            i += 1
    path.write_text(
        json.dumps({"schema_version": 1, "exported_at": now, "entries": entries}, indent=2)
        + "\n",
        encoding="utf-8",
    )


def prepare_tools_home(plugin: str, home: Path) -> None:
    src = REPO_ROOT / "tools" / plugin
    if not src.is_dir():
        src = REPO_ROOT / "plugins" / plugin
    dest_parent = home / ".config" / "naitv-mcp" / "tools"
    dest_parent.mkdir(parents=True, exist_ok=True)
    dest = dest_parent / plugin
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    dest.symlink_to(src, target_is_directory=True)
    link_tools_lib(home)


@contextmanager
def mcp_session(*, plugins: list[str]) -> Iterator[MCPClient]:
    """Start naitv-mcp serve with optional plugin tools seeded."""
    with tempfile.TemporaryDirectory(prefix="naitv-l5-mcp-") as tmp:
        home = Path(tmp)
        db = home / "eval.db"
        for plugin in plugins:
            prepare_tools_home(plugin, home)
        seed = home / "seed.json"
        if plugins:
            build_plugin_seed(plugins, seed)
        else:
            seed.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "exported_at": datetime.now(timezone.utc).isoformat(),
                        "entries": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        imp = subprocess.run(
            ["naitv-mcp", "import", str(seed), "--db", str(db), "--replace"],
            capture_output=True,
            text=True,
            check=False,
        )
        if imp.returncode != 0:
            raise RuntimeError(f"naitv-mcp import failed: {imp.stderr}")

        env = os.environ.copy()
        env["HOME"] = str(home)
        env["XDG_CACHE_HOME"] = str(home / ".cache")
        env["NAITV_MCP_DB"] = str(db)
        proc = subprocess.Popen(
            ["naitv-mcp", "serve", "--db", str(db)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        client = MCPClient(proc)
        try:
            client.request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "l5-eval", "version": "0"},
                },
            )
            client.notify("notifications/initialized")
            yield client
        finally:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.terminate()


def list_plugin_tools(
    client: MCPClient, *, plugins: list[str] | None = None
) -> list[dict[str, Any]]:
    listed = client.request("tools/list")
    tools = listed.get("tools") or []
    if plugins is None:
        return tools
    allow = plugin_tool_names(plugins)
    return [t for t in tools if t.get("name") in allow]


# Back-compat for imports that still expect a constant; prefer plugin_tool_names().
PLUGIN_TOOL_NAMES = frozenset(
    tool_names(load_manifest("structural-anchor"))
    if (REPO_ROOT / "plugins" / "structural-anchor" / "plugin.json").is_file()
    else ()
)
