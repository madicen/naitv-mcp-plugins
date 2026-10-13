"""L5 agent tool-loop: MCP tools + optional Ollama function calling."""
from __future__ import annotations

import json
import os
import random
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from mcp_session import MCPClient, list_plugin_tools, plugin_tool_names

FIXTURES = Path(__file__).resolve().parents[2] / "testing" / "fixtures"
MAX_TURNS = 4


def _mcp_to_ollama_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for tool in tools:
        schema = tool.get("inputSchema") or {"type": "object", "properties": {}}
        out.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description") or tool["name"],
                    "parameters": schema,
                },
            }
        )
    return out


def _ollama_request(
    host: str, payload: dict[str, Any], *, timeout: float = 180
) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def toolstub_with_mcp(
    client: MCPClient,
    task: dict[str, Any],
    *,
    condition: str,
    plugins: list[str] | None = None,
) -> dict[str, Any]:
    """Deterministic agent that uses seeded plugin tools when available."""
    fixture_root = str((FIXTURES / task["fixture"]).resolve())
    calls: list[dict[str, Any]] = []
    available = {
        t["name"] for t in list_plugin_tools(client, plugins=plugins or None)
    }

    if task.get("control"):
        text = (
            "The add function in pkg/greeter.py returns the sum of its two integer arguments."
        )
        return {
            "final_answer": text,
            "turns": 1,
            "tool_calls": calls,
            "agent": "stub",
            "condition": condition,
        }

    if condition != "treatment" or not available:
        return {
            "final_answer": "I am not sure without project-map tools.",
            "turns": 1,
            "tool_calls": calls,
            "agent": "stub",
            "condition": condition,
        }

    tid = task["id"]
    if tid.startswith("nav-002") and "list_languages" in available:
        name = "list_languages"
    elif "get_project_map" in available:
        name = "get_project_map"
    else:
        name = next(iter(available))

    args = {"root_path": fixture_root, "depth": 3}
    text, is_err = client.call_tool(name, args)
    calls.append({"name": name, "arguments": args, "is_error": is_err})
    if is_err:
        return {
            "final_answer": f"Tool {name} failed: {text[:200]}",
            "turns": 1,
            "tool_calls": calls,
            "agent": "stub",
            "condition": condition,
        }

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {
            "final_answer": text[:500],
            "turns": 1,
            "tool_calls": calls,
            "agent": "stub",
            "condition": condition,
        }

    if name == "list_languages":
        langs = payload.get("languages") or []
        ids = [str(row.get("id", "")) for row in langs]
        primary = payload.get("primary")
        answer = (
            f"Languages present: {', '.join(ids)}. Primary language by file count: {primary}."
        )
    else:
        # get_project_map → task-specific brief answer
        packages = payload.get("packages") or []
        if tid.startswith("nav-001"):
            hit = None
            for pkg in packages:
                for sym in pkg.get("symbols") or []:
                    if sym.get("name") == "Greeter":
                        hit = (pkg.get("path"), sym)
                        break
                if hit:
                    break
            if hit:
                path, sym = hit
                answer = (
                    f"Greeter is a {sym.get('kind')} defined under {path}/greeter.py "
                    f"(symbol Greeter)."
                )
            else:
                answer = "Greeter class not found in project map."
        elif tid.startswith("nav-003"):
            names = [str(p.get("name")) for p in packages]
            exported = None
            for pkg in packages:
                if pkg.get("name") == "greeter":
                    for sym in pkg.get("symbols") or []:
                        if sym.get("name") == "Add":
                            exported = "Add"
                            break
            answer = (
                f"Go packages include: {', '.join(names)}. "
                f"Exported function from greeter: {exported or 'unknown'}."
            )
        else:
            answer = json.dumps({"packages": len(packages)}, separators=(",", ":"))

    return {
        "final_answer": answer,
        "turns": 1,
        "tool_calls": calls,
        "agent": "stub",
        "condition": condition,
    }


def ollama_with_mcp(
    client: MCPClient | None,
    task: dict[str, Any],
    *,
    condition: str,
    seed: int,
    plugins: list[str] | None = None,
) -> dict[str, Any]:
    model = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    fixture_root = str((FIXTURES / task["fixture"]).resolve())
    allow = plugin_tool_names(plugins or [])

    tools_mcp: list[dict[str, Any]] = []
    if client is not None and condition == "treatment":
        tools_mcp = list_plugin_tools(client, plugins=plugins or None)
        rng = random.Random(seed)
        rng.shuffle(tools_mcp)  # plan: randomize tool order per run

    ollama_tools = _mcp_to_ollama_tools(tools_mcp) if tools_mcp else None

    system = (
        "You are a careful coding assistant working on a local fixture repo. "
        "Answer briefly and only name symbols that exist. "
        "When tools are available, use them before answering navigation questions. "
        "When you are done, reply with the final answer as plain text (no tool call)."
    )
    user = (
        f"Fixture repo root (absolute): {fixture_root}\n"
        f"Condition: {condition}\n\n"
        f"Task: {task['request']}\n"
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    calls: list[dict[str, Any]] = []

    try:
        for turn in range(1, MAX_TURNS + 1):
            payload: dict[str, Any] = {
                "model": model,
                "stream": False,
                "options": {"temperature": 0, "seed": seed},
                "messages": messages,
            }
            if ollama_tools:
                payload["tools"] = ollama_tools
            data = _ollama_request(host, payload)
            message = data.get("message") or {}
            tool_calls = message.get("tool_calls") or []
            content = message.get("content") or ""

            if tool_calls and client is not None:
                messages.append(
                    {
                        "role": "assistant",
                        "content": content,
                        "tool_calls": tool_calls,
                    }
                )
                for tc in tool_calls:
                    fn = tc.get("function") or {}
                    name = fn.get("name") or ""
                    raw_args = fn.get("arguments") or {}
                    if isinstance(raw_args, str):
                        try:
                            args = json.loads(raw_args)
                        except json.JSONDecodeError:
                            args = {}
                    else:
                        args = dict(raw_args)
                    # Force fixture root if model omits/wrong path.
                    if name in allow and "root_path" not in args:
                        args["root_path"] = fixture_root
                    text, is_err = client.call_tool(name, args)
                    calls.append(
                        {
                            "name": name,
                            "arguments": args,
                            "is_error": is_err,
                            "turn": turn,
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "content": text if not is_err else f"ERROR: {text}",
                        }
                    )
                continue

            return {
                "final_answer": content.strip(),
                "turns": turn,
                "tool_calls": calls,
                "agent": "ollama",
                "model": model,
                "condition": condition,
            }

        return {
            "final_answer": content.strip() if "content" in locals() else "",
            "turns": MAX_TURNS,
            "tool_calls": calls,
            "agent": "ollama",
            "model": model,
            "condition": condition,
            "error": "max turns reached",
        }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
        return {
            "final_answer": "",
            "turns": 0,
            "tool_calls": calls,
            "agent": "ollama",
            "model": model,
            "condition": condition,
            "error": str(exc),
        }
