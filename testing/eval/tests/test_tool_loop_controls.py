"""Control tasks must not receive MCP tools under treatment."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from tool_loop import ollama_with_mcp


def test_ollama_control_treatment_offers_no_tools() -> None:
    client = MagicMock()
    task = {
        "id": "valtest-v2-ctl-002-exists",
        "fixture": "build-mini",
        "control": True,
        "request": "Confirm README exists; include README.",
    }
    captured: list[dict[str, Any]] = []

    def fake_request(_host: str, payload: dict[str, Any]) -> dict[str, Any]:
        captured.append(payload)
        return {"message": {"content": "README present", "tool_calls": []}}

    with (
        patch("tool_loop.list_plugin_tools", return_value=[{"name": "run_validation"}]),
        patch("tool_loop._ollama_request", side_effect=fake_request),
    ):
        out = ollama_with_mcp(
            client,
            task,
            condition="treatment",
            seed=42,
            plugins=["validate-and-test"],
        )

    assert out["final_answer"] == "README present"
    assert out["tool_calls"] == []
    assert captured and "tools" not in captured[0]
    client.call_tool.assert_not_called()


def test_ollama_non_control_treatment_still_offers_tools() -> None:
    client = MagicMock()
    task = {
        "id": "valtest-v2-001-make",
        "fixture": "build-mini",
        "control": False,
        "request": "Detect the build system.",
    }
    captured: list[dict[str, Any]] = []

    def fake_request(_host: str, payload: dict[str, Any]) -> dict[str, Any]:
        captured.append(payload)
        return {"message": {"content": "make", "tool_calls": []}}

    with (
        patch(
            "tool_loop.list_plugin_tools",
            return_value=[
                {
                    "name": "detect_build_system",
                    "description": "detect",
                    "inputSchema": {"type": "object", "properties": {}},
                }
            ],
        ),
        patch("tool_loop._ollama_request", side_effect=fake_request),
    ):
        ollama_with_mcp(
            client,
            task,
            condition="treatment",
            seed=1,
            plugins=["validate-and-test"],
        )

    assert captured and "tools" in captured[0]
    assert captured[0]["tools"][0]["function"]["name"] == "detect_build_system"
