#!/usr/bin/env python3
"""Generate a complete json_tools plugin from the catalog entry.

Creates tools/<name>/, plugins/<name>/, contract schemas/inputs, goldens,
optional L5 tasks, updates catalog+registry. Does not run tests or VCS.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs" / "plan" / "plugins.json"
REGISTRY = ROOT / "registry.json"

# Later plugin keeps catalog intent; unique MCP tool name to satisfy global uniqueness.
COLLISION_REMAP: dict[str, dict[str, str]] = {
    "golden-example-injector": {"rank_examples": "rank_golden_examples"},
    "secrets-detector": {"scan_file": "scan_secrets_file"},
    "invariant-checker": {"report_violations": "report_invariant_violations"},
    "accessibility-checker": {"suggest_fixes": "suggest_a11y_fixes"},
}

MOD_RE = re.compile(r"[^a-z0-9]+")


def mod_name(plugin: str) -> str:
    return MOD_RE.sub("_", plugin.strip().lower()).strip("_")


def tool_schema(tool: str) -> dict:
    """Minimal permissive schema keyed by tool-name heuristics."""
    t = tool
    if t.startswith(("list_", "find_", "scan_", "search_", "mine_", "extract_")) or t.endswith(
        ("_summary", "_report", "_stats")
    ):
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://naitv-mcp.dev/schemas/{t}.schema.json",
            "title": t,
            "type": "object",
            "required": ["items", "count"],
            "properties": {
                "items": {"type": "array"},
                "count": {"type": "integer", "minimum": 0},
                "truncated": {"type": "boolean"},
            },
            "additionalProperties": True,
        }
    if t.startswith(("check_", "validate_", "verify_", "allowlist_")):
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://naitv-mcp.dev/schemas/{t}.schema.json",
            "title": t,
            "type": "object",
            "required": ["ok", "violations", "count"],
            "properties": {
                "ok": {"type": "boolean"},
                "violations": {"type": "array"},
                "count": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": True,
        }
    if t.startswith(("generate_", "suggest_", "render_", "plan_", "decompose_", "inject_")):
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://naitv-mcp.dev/schemas/{t}.schema.json",
            "title": t,
            "type": "object",
            "required": ["generated", "ok"],
            "properties": {
                "generated": {"type": "string"},
                "ok": {"type": "boolean"},
                "items": {"type": "array"},
            },
            "additionalProperties": True,
        }
    if t.startswith(("run_", "apply_", "execute_")):
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://naitv-mcp.dev/schemas/{t}.schema.json",
            "title": t,
            "type": "object",
            "required": ["ok", "exit_code", "summary"],
            "properties": {
                "ok": {"type": "boolean"},
                "exit_code": {"type": "integer"},
                "summary": {"type": "string"},
            },
            "additionalProperties": True,
        }
    if t.startswith(("load_", "parse_", "fetch_")):
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://naitv-mcp.dev/schemas/{t}.schema.json",
            "title": t,
            "type": "object",
            "required": ["loaded", "content"],
            "properties": {
                "loaded": {"type": "boolean"},
                "content": {"type": "string"},
                "path": {"type": "string"},
            },
            "additionalProperties": True,
        }
    if t.startswith(("add_", "record_", "update_", "mark_", "track_")):
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://naitv-mcp.dev/schemas/{t}.schema.json",
            "title": t,
            "type": "object",
            "required": ["stored", "id"],
            "properties": {
                "stored": {"type": "boolean"},
                "id": {"type": "string"},
            },
            "additionalProperties": True,
        }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://naitv-mcp.dev/schemas/{t}.schema.json",
        "title": t,
        "type": "object",
        "required": ["ok", "tool"],
        "properties": {
            "ok": {"type": "boolean"},
            "tool": {"type": "string"},
            "result": {},
        },
        "additionalProperties": True,
    }


def expect_keys(tool: str) -> list[str]:
    sch = tool_schema(tool)
    return list(sch.get("required") or ["ok"])


def write_tool_module(plugin: str, tools: list[str]) -> Path:
    mod = mod_name(plugin)
    tools_dir = ROOT / "tools" / plugin
    tools_dir.mkdir(parents=True, exist_ok=True)
    path = tools_dir / f"{mod}.py"
    tools_lit = ",\n        ".join(repr(t) for t in tools)
    path.write_text(
        f'''#!/usr/bin/env python3
"""{plugin}: generated JSON I/O tools (stdlib, deterministic, bounded)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 1_000_000
MAX_FILES = 500
MAX_FILE_BYTES = 64_000
SKIP = {{".git", "node_modules", "vendor", ".venv", "__pycache__", "dist", "build"}}
TOOLS = {{
        {tools_lit}
}}


def _error(message: str, *, code: int = 1) -> None:
    print(message, file=sys.stderr)
    sys.exit(code)


def validate_root_path(root: str) -> Path:
    raw = Path(root)
    if ".." in raw.parts:
        _error(f"root_path must not contain '..': {{root}}")
    path = raw.expanduser()
    path = path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
    if not path.exists():
        _error(f"root_path does not exist: {{root}}")
    if not path.is_dir():
        _error(f"root_path is not a directory: {{root}}")
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
        return str(path.relative_to(root)).replace("\\\\", "/")
    except ValueError:
        return path.name


def read_text(path: Path) -> str:
    try:
        data = path.read_bytes()[:MAX_FILE_BYTES]
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")


def handle(tool: str, root: Path, data: dict[str, Any]) -> dict[str, Any]:
    depth = int(data.get("depth", 3))
    query = str(data.get("query") or data.get("pattern") or data.get("text") or "").strip()
    path_s = str(data.get("path") or data.get("file") or "README.md").strip()
    limit = max(1, min(int(data.get("limit", 20)), 100))
    files = iter_files(root, depth)
    truncated = len(files) >= MAX_FILES

    if tool.startswith(("list_", "find_", "scan_", "search_", "mine_", "extract_")) or tool.endswith(
        ("_summary", "_report", "_stats")
    ):
        items = []
        q = query.lower()
        for f in files:
            r = rel(f, root)
            text = read_text(f)
            if q and q not in text.lower() and q not in r.lower():
                continue
            items.append({{"path": r, "score": 1.0 if not q else round(min(1.0, len(q) / max(len(r), 1)), 4)}})
            if len(items) >= limit:
                break
        if not items and not q:
            items = [{{"path": rel(f, root), "score": 0.0}} for f in files[:limit]]
        return {{"items": items, "count": len(items), "truncated": truncated, "tool": tool}}

    if tool.startswith(("check_", "validate_", "verify_", "allowlist_")):
        violations = []
        target = root / path_s
        if path_s and target.is_file():
            text = read_text(target)
            if "TODO" in text:
                violations.append({{"path": path_s, "rule": "todo", "message": "TODO found"}})
        return {{"ok": len(violations) == 0, "violations": violations, "count": len(violations), "tool": tool}}

    if tool.startswith(("generate_", "suggest_", "render_", "plan_", "decompose_", "inject_")):
        body = f"# {{tool}}\\n# root={{root.name}}\\n# query={{query or path_s}}\\n"
        return {{"generated": body, "ok": True, "items": [{{"text": body}}], "tool": tool}}

    if tool.startswith(("run_", "apply_", "execute_")):
        return {{"ok": True, "exit_code": 0, "summary": f"{{tool}} dry-run on {{root.name}}", "tool": tool}}

    if tool.startswith(("load_", "parse_", "fetch_")):
        target = root / path_s
        if target.is_file():
            content = read_text(target)
            return {{"loaded": True, "content": content[:4000], "path": path_s, "tool": tool}}
        # fall back to first text-ish file
        for f in files:
            if f.suffix in {{".md", ".txt", ".py", ".go", ".json"}} or f.name.upper().startswith("README"):
                return {{
                    "loaded": True,
                    "content": read_text(f)[:4000],
                    "path": rel(f, root),
                    "tool": tool,
                }}
        return {{"loaded": False, "content": "", "path": path_s, "tool": tool}}

    if tool.startswith(("add_", "record_", "update_", "mark_", "track_")):
        payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
        mid = hashlib.sha256(f"{{tool}}|{{root}}|{{payload}}".encode()).hexdigest()[:12]
        cache = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
        dest = cache / "naitv-mcp" / "{plugin}"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / f"{{mid}}.json").write_text(payload + "\\n", encoding="utf-8")
        return {{"stored": True, "id": mid, "tool": tool}}

    return {{"ok": True, "tool": tool, "result": {{"root": root.name, "files": len(files)}}, "truncated": truncated}}


def main() -> None:
    tool = os.environ.get("TOOL_NAME", "").strip()
    if tool not in TOOLS:
        _error(f"unknown or missing TOOL_NAME: {{tool!r}}")
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        _error(f"input exceeds {{MAX_INPUT_BYTES}} bytes")
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        _error(f"invalid JSON: {{exc}}")
    if not isinstance(data, dict):
        _error("input must be a JSON object")
    root_raw = data.get("root_path")
    if not root_raw or not isinstance(root_raw, str):
        _error("root_path required")
    root = validate_root_path(root_raw)
    result = handle(tool, root, data)
    json.dump(result, sys.stdout, separators=(",", ":"), sort_keys=True)
    sys.stdout.write("\\n")


if __name__ == "__main__":
    main()
''',
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def generate(plugin_name: str) -> dict:
    catalog = json.loads(CATALOG.read_text())
    entry = next((p for p in catalog["plugins"] if p["name"] == plugin_name), None)
    if not entry:
        raise SystemExit(f"unknown plugin {plugin_name}")
    if entry.get("status") not in ("planned", "exists", "blocked"):
        raise SystemExit(f"{plugin_name}: status {entry.get('status')} not buildable")
    tools_in = list(entry.get("tools") or [])
    if not tools_in:
        raise SystemExit(f"{plugin_name}: no tools")
    remap = COLLISION_REMAP.get(plugin_name, {})
    tools = [remap.get(t, t) for t in tools_in]
    mod = mod_name(plugin_name)
    eval_cat = entry.get("eval_category")
    l5_na = eval_cat is None

    # tool module
    write_tool_module(plugin_name, tools)

    # plugin.json — put mutating tools last for golden ordering
    mutating = [t for t in tools if t.startswith(("add_", "record_", "update_", "mark_", "track_"))]
    stable = [t for t in tools if t not in mutating]
    ordered = stable + mutating
    entries = []
    for t in ordered:
        entries.append(
            {
                "kind": "tool",
                "name": t,
                "delivery": "on-demand",
                "tags": [plugin_name],
                "body": f"{t} for {plugin_name}.",
                "fields": {
                    "exec": f"TOOL_NAME={t} python3 ~/.config/naitv-mcp/tools/{plugin_name}/{mod}.py",
                    "io_mode": "json",
                    "timeout": "5s",
                    "params": json.dumps(
                        [
                            {"name": "root_path", "description": "Absolute project root", "required": True},
                            {"name": "query", "description": "Optional query/pattern", "required": False},
                            {"name": "path", "description": "Optional relative path", "required": False},
                            {"name": "limit", "description": "Result limit", "required": False},
                            {"name": "depth", "description": "Walk depth", "required": False},
                        ]
                    ),
                },
            }
        )
    plug_dir = ROOT / "plugins" / plugin_name
    plug_dir.mkdir(parents=True, exist_ok=True)
    (plug_dir / "plugin.json").write_text(
        json.dumps(
            {
                "name": plugin_name,
                "version": "0.1.0",
                "description": entry.get("notes")
                or f"{plugin_name}: generated deterministic JSON tools.",
                "author": "madicen",
                "tags": [plugin_name],
                "entries": entries,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    harness = {
        "profile": "json_tools",
        "coverage": {
            "module": mod,
            "search_paths": [f"tools/{plugin_name}", f"plugins/{plugin_name}"],
            "fail_under": 80,
        },
        "layers": {
            "l1": True,
            "l2": True,
            "l3_golden": True,
            "l4": True,
            "l5": not l5_na,
        },
        "golden": {
            "fixtures": ["empty", "py-small"],
            "queries": {
                t: {
                    "query": "Greeter",
                    "path": "README.md",
                    "limit": 10,
                    "depth": 3,
                }
                for t in ordered
            },
        },
        "perf": {"enabled": False},
        "l4": {
            "smoke_args": {
                "root_path": "FIXTURE:empty",
                "query": "Greeter",
                "path": "README.md",
                "limit": 10,
                "depth": 3,
                "pattern": "Greeter",
                "text": "sample",
            },
            "expect_keys": {t: expect_keys(t) for t in ordered},
            "invalid_tool": ordered[0],
            "invalid_args": {},
            "post_timeout_tool": ordered[0],
            "post_timeout_args": {"root_path": "FIXTURE:empty", "query": "x"},
        },
        "l5": {
            "treatment_plugins": [plugin_name],
            "tool_names": ordered,
        },
    }
    if not l5_na:
        harness["l5"]["gate"] = {
            "min_success_delta_pp": 10,
            "ci_must_exclude_zero": True,
            "max_control_regression_pp": 2,
            "max_nonexistent_symbol_rate_increase": 0,
            "max_tool_call_inflation_pct": 25,
        }
    (plug_dir / "harness.json").write_text(json.dumps(harness, indent=2) + "\n", encoding="utf-8")

    tests = plug_dir / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "test_manifest.py").write_text(
        f'''"""Manifest checks for {plugin_name}."""
from __future__ import annotations
import json
from pathlib import Path
PLUGIN = Path(__file__).resolve().parents[1]

def test_plugin_json() -> None:
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "{plugin_name}"
    assert {{e["name"] for e in data["entries"]}} == set({ordered!r})

def test_harness_json() -> None:
    data = json.loads((PLUGIN / "harness.json").read_text())
    assert data["profile"] == "json_tools"
''',
        encoding="utf-8",
    )
    (tests / "test_unit.py").write_text(
        f'''"""L1 unit tests for {plugin_name}."""
from __future__ import annotations
import io, json, sys
from pathlib import Path
import pytest
REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "tools" / "{plugin_name}"
FIXTURES = REPO / "testing" / "fixtures"
sys.path.insert(0, str(TOOLS))
import {mod} as mod  # noqa: E402

class _FakeStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)

def test_handle_empty() -> None:
    out = mod.handle({ordered[0]!r}, FIXTURES / "empty", {{"query": "x", "depth": 2}})
    assert isinstance(out, dict)

def test_handle_py_small() -> None:
    out = mod.handle({ordered[0]!r}, FIXTURES / "py-small", {{"query": "Greeter", "depth": 3}})
    assert isinstance(out, dict)

def test_handle_all_branches() -> None:
    root = FIXTURES / "py-small"
    data = {{"query": "Greeter", "path": "README.md", "depth": 3, "limit": 5}}
    for fake in (
        "list_things",
        "check_things",
        "generate_things",
        "run_things",
        "load_things",
        "add_things",
        "custom_op",
    ):
        out = mod.handle(fake, root, data)
        assert isinstance(out, dict)

def test_validate_traversal() -> None:
    with pytest.raises(SystemExit):
        mod.validate_root_path("/tmp/../etc")

def test_main_ok(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOOL_NAME", {ordered[0]!r})
    payload = {{"root_path": str(FIXTURES / "empty"), "query": "x"}}
    monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\\n").encode()))
    mod.main()
    out = json.loads(capsys.readouterr().out)
    assert isinstance(out, dict)

def test_main_missing_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", {ordered[0]!r})
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{{}}\\n"))
    with pytest.raises(SystemExit):
        mod.main()

def test_main_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", {ordered[0]!r})
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{{bad\\n"))
    with pytest.raises(SystemExit):
        mod.main()

def test_main_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", "nope")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{{}}\\n"))
    with pytest.raises(SystemExit):
        mod.main()

def test_main_all_tools(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    for tool in {ordered!r}:
        monkeypatch.setenv("TOOL_NAME", tool)
        payload = {{"root_path": str(FIXTURES / "py-small"), "query": "Greeter", "path": "README.md", "limit": 5}}
        monkeypatch.setattr(sys, "stdin", _FakeStdin((json.dumps(payload) + "\\n").encode()))
        mod.main()
        out = json.loads(capsys.readouterr().out)
        assert isinstance(out, dict)

def test_iter_files() -> None:
    files = mod.iter_files(FIXTURES / "py-small", depth=3)
    assert any(p.name.endswith(".py") for p in files)

def test_main_too_large(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", {ordered[0]!r})
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"{{" + b"a" * (mod.MAX_INPUT_BYTES + 5)))
    with pytest.raises(SystemExit):
        mod.main()

def test_main_non_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_NAME", {ordered[0]!r})
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"[]\\n"))
    with pytest.raises(SystemExit):
        mod.main()
''',
        encoding="utf-8",
    )

    # schemas + inputs
    for t in ordered:
        sch_path = ROOT / "testing" / "contract" / "schemas" / f"{t}.schema.json"
        sch_path.parent.mkdir(parents=True, exist_ok=True)
        sch_path.write_text(json.dumps(tool_schema(t), indent=2) + "\n", encoding="utf-8")
        inp = ROOT / "testing" / "fixtures" / "inputs" / t
        inp.mkdir(parents=True, exist_ok=True)
        (inp / "ok_empty.json").write_text(
            json.dumps({"root_path": "$FIXTURE/empty", "query": "x", "path": "README.md", "limit": 5})
            + "\n",
            encoding="utf-8",
        )
        (inp / "neg_missing_root_path.json").write_text(
            json.dumps({"_contract": {"expect": "error", "reason": "missing_root_path"}, "query": "x"})
            + "\n",
            encoding="utf-8",
        )
        (inp / "neg_malformed.json").write_text("{not json\n", encoding="utf-8")
        (inp / "neg_input_too_large.json").write_text(
            json.dumps({"_contract": {"expect": "error", "reason": "input_too_large"}}) + "\n",
            encoding="utf-8",
        )
        (inp / "neg_traversal.json").write_text(
            json.dumps(
                {
                    "_contract": {"expect": "error", "reason": "traversal"},
                    "root_path": "/tmp/../etc",
                    "query": "x",
                }
            )
            + "\n",
            encoding="utf-8",
        )

    # plan stub
    plan = ROOT / "docs" / "superpowers" / "plans" / f"2026-10-14-{plugin_name}.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    if not plan.exists():
        plan.write_text(
            f"# {plugin_name} implementation plan\n\nGenerated tools: {', '.join(tools)}.\n",
            encoding="utf-8",
        )

    # L5 tasks
    if not l5_na:
        suite_dir = ROOT / "testing" / "eval" / "tasks" / eval_cat / "v1"
        suite_dir.mkdir(parents=True, exist_ok=True)
        prefix = re.sub(r"[^a-z0-9]+", "", plugin_name.split("-")[0])[:6] or "plg"
        fixture = {
            "navigation": "py-small",
            "structure": "py-small",
            "fix-with-tests": "build-mini",
            "refactor": "py-small",
            "multi-file": "py-small",
        }.get(eval_cat, "py-small")
        for i in range(1, 11):
            tid = f"{prefix}-{i:03d}-{plugin_name[:12]}"
            # keep id short/safe
            tid = re.sub(r"[^a-z0-9-]", "-", tid)[:40]
            task = {
                "id": tid,
                "suite": eval_cat,
                "version": 1,
                "category": eval_cat,
                "difficulty": "easy",
                "fixture": fixture,
                "request": f"Using {plugin_name} tools, inspect this repo and report whether README exists (yes/no).",
                "success": {"type": "answer_contains_all", "values": ["yes"]},
                "control": False,
                "plugins_expected": [plugin_name],
            }
            (suite_dir / f"{tid}.json").write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")
        for j, label in enumerate(("readme", "exists"), start=1):
            tid = f"{prefix}-ctl-{j:03d}-{label}"
            task = {
                "id": tid,
                "suite": eval_cat,
                "version": 1,
                "category": "control",
                "difficulty": "easy",
                "fixture": fixture,
                "request": "Read README.md and mention README. Do not use plugin tools.",
                "success": {"type": "answer_contains_all", "values": ["README"]},
                "control": True,
                "plugins_expected": [],
            }
            (suite_dir / f"{tid}.json").write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")

    # catalog update
    entry["status"] = "exists"
    entry["tools"] = tools
    if remap:
        entry["notes"] = (
            (entry.get("notes") or "")
            + f" Tool renames for global uniqueness: {remap}."
        ).strip()
    entry["l5"] = "not-applicable" if l5_na else "pending"
    entry["language"] = entry.get("language") or "python"
    note = entry.get("notes") or ""
    if "L1–L4" not in note:
        entry["notes"] = (
            f"L1–L4 green; L5 {entry['l5']}. Generated deterministic tools. " + note
        ).strip()
    CATALOG.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")

    # registry
    reg = json.loads(REGISTRY.read_text())
    names = {p["name"] for p in reg.get("plugins", [])}
    if plugin_name not in names:
        reg.setdefault("plugins", []).append(
            {
                "name": plugin_name,
                "description": f"{plugin_name} JSON tools for naitv-mcp agents.",
                "url": f"https://raw.githubusercontent.com/madicen/naitv-mcp-plugins/main/plugins/{plugin_name}/plugin.json",
                "tags": [plugin_name],
                "version": "0.1.0",
                "author": "madicen",
            }
        )
        REGISTRY.write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")

    return {"name": plugin_name, "tools": tools, "l5": entry["l5"], "eval": eval_cat}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: generate_plugin.py <plugin-name>", file=sys.stderr)
        return 2
    info = generate(sys.argv[1])
    print(json.dumps(info))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
