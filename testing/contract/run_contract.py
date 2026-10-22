#!/usr/bin/env python3
"""L2 contract harness: run plugin tool entries exactly as naitv-mcp (sh -c)."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "testing"))
from plugin_harness import link_tools_lib  # noqa: E402
SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"
FIXTURES_DIR = REPO_ROOT / "testing" / "fixtures"
INPUTS_DIR = FIXTURES_DIR / "inputs"
MAX_STDOUT_BYTES = 1_000_000
DETERMINISM_IGNORE_KEYS = frozenset({"cached"})

# Matches timeout fields like "30s", "1.5s", "30"
_TIMEOUT_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*s?$", re.IGNORECASE)


class Report:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.failures = 0
        self.not_implemented = 0
        self.passed = 0

    def ok(self, msg: str) -> None:
        self.passed += 1
        self.lines.append(f"  PASS  {msg}")

    def fail(self, msg: str) -> None:
        self.failures += 1
        self.lines.append(f"  FAIL  {msg}")

    def skip_ni(self, msg: str) -> None:
        self.not_implemented += 1
        self.lines.append(f"  NOT IMPLEMENTED  {msg}")

    def section(self, msg: str) -> None:
        self.lines.append(msg)

    def dump(self) -> None:
        print("\n".join(self.lines))
        print()
        print(
            f"Summary: {self.passed} passed, {self.failures} failed, "
            f"{self.not_implemented} not implemented"
        )


def parse_timeout(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    match = _TIMEOUT_RE.match(text)
    if not match:
        return None
    return float(match.group(1))


def load_plugin(plugin_name: str) -> dict[str, Any]:
    path = REPO_ROOT / "plugins" / plugin_name / "plugin.json"
    if not path.is_file():
        raise SystemExit(f"missing plugin manifest: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def tool_entries(plugin: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for entry in plugin.get("entries", []):
        if entry.get("kind") == "tool":
            out.append(entry)
    return out


def expand_exec(exec_str: str, home: Path) -> str:
    """Expand ~ against a harness-controlled HOME (naitv install layout)."""
    return os.path.expanduser(exec_str.replace("~", str(home)))


def prepare_home(plugin_name: str, home: Path) -> Path | None:
    """Symlink repo tools into ~/.config/naitv-mcp/tools/<plugin>/ if present."""
    src = REPO_ROOT / "tools" / plugin_name
    if not src.is_dir():
        return None
    dest_parent = home / ".config" / "naitv-mcp" / "tools"
    dest_parent.mkdir(parents=True, exist_ok=True)
    dest = dest_parent / plugin_name
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    dest.symlink_to(src, target_is_directory=True)
    link_tools_lib(home)
    return dest


def exec_script_path(exec_str: str, home: Path) -> Path | None:
    """Best-effort extract of the python script path from an exec string."""
    expanded = expand_exec(exec_str, home)
    # TOOL_NAME=... python3 /path/to/script.py
    parts = expanded.split()
    for part in reversed(parts):
        if part.endswith(".py") or part.endswith(".sh"):
            return Path(part)
    return None


def validate_schema(instance: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Minimal JSON Schema draft 2020-12 checker for our tool schemas."""
    errors: list[str] = []

    def typematch(value: Any, declared: Any) -> bool:
        if isinstance(declared, list):
            return any(typematch(value, item) for item in declared)
        if declared == "object":
            return isinstance(value, dict)
        if declared == "array":
            return isinstance(value, list)
        if declared == "string":
            return isinstance(value, str)
        if declared == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if declared == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if declared == "boolean":
            return isinstance(value, bool)
        if declared == "null":
            return value is None
        return True

    stype = schema.get("type")
    if stype is not None and not typematch(instance, stype):
        errors.append(f"{path}: expected type {stype}, got {type(instance).__name__}")
        return errors

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: value {instance!r} not in enum {schema['enum']}")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: {instance} < minimum {schema['minimum']}")

    if isinstance(instance, str) and "minLength" in schema:
        if len(instance) < schema["minLength"]:
            errors.append(f"{path}: string shorter than minLength")

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required property {key!r}")
        props = schema.get("properties", {})
        addl = schema.get("additionalProperties", True)
        for key, value in instance.items():
            if key in props:
                errors.extend(validate_schema(value, props[key], f"{path}.{key}"))
            elif addl is False:
                errors.append(f"{path}: unexpected property {key!r}")
            elif isinstance(addl, dict):
                errors.extend(validate_schema(value, addl, f"{path}.{key}"))

    if isinstance(instance, list) and "items" in schema:
        item_schema = schema["items"]
        for i, value in enumerate(instance):
            errors.extend(validate_schema(value, item_schema, f"{path}[{i}]"))

    return errors


def strip_for_determinism(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: strip_for_determinism(v)
            for k, v in obj.items()
            if k not in DETERMINISM_IGNORE_KEYS
        }
    if isinstance(obj, list):
        return [strip_for_determinism(v) for v in obj]
    return obj


def resolve_placeholders(payload: Any, fixtures_root: Path) -> Any:
    if isinstance(payload, str):
        if payload.startswith("$FIXTURE/"):
            return str((fixtures_root / payload[len("$FIXTURE/") :]).resolve())
        if payload == "$MISSING_PATH":
            return str((fixtures_root / "__does_not_exist__" / "nope").resolve())
        if payload == "$TRAVERSAL_PATH":
            # Keep literal ".." segments so tools must reject or normalize.
            return str(fixtures_root / "py-small" / ".." / ".." / ".." / "etc" / "passwd")
        return payload
    if isinstance(payload, list):
        return [resolve_placeholders(v, fixtures_root) for v in payload]
    if isinstance(payload, dict):
        return {k: resolve_placeholders(v, fixtures_root) for k, v in payload.items()}
    return payload


def load_input_case(path: Path) -> tuple[bytes, dict[str, Any]]:
    """Return (stdin_bytes, contract meta). Meta defaults to expect success."""
    raw = path.read_bytes()
    meta: dict[str, Any] = {"expect": "success", "name": path.stem}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        meta["expect"] = "error"
        meta["reason"] = "malformed_json"
        return raw if raw.endswith(b"\n") else raw + b"\n", meta

    if isinstance(data, dict) and "_contract" in data:
        meta = {**meta, **data.pop("_contract")}

    if meta.get("reason") == "input_too_large":
        # Body built later in the runner; leave a stub.
        return b"{}\n", meta

    resolved = resolve_placeholders(data, FIXTURES_DIR)
    stdin = (json.dumps(resolved, separators=(",", ":")) + "\n").encode("utf-8")
    return stdin, meta


def run_once(
    exec_str: str,
    stdin: bytes,
    timeout: float,
    home: Path,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    # Avoid polluting the developer's real cache during contract runs.
    env["XDG_CACHE_HOME"] = str(home / ".cache")
    if env_extra:
        env.update(env_extra)
    expanded = expand_exec(exec_str, home)
    return subprocess.run(
        ["sh", "-c", expanded],
        input=stdin,
        capture_output=True,
        timeout=timeout,
        env=env,
        cwd=str(REPO_ROOT),
        check=False,
    )


def check_stdout_contract(
    stdout: bytes, expect_success: bool
) -> tuple[Any | None, list[str]]:
    errors: list[str] = []
    if len(stdout) > MAX_STDOUT_BYTES:
        errors.append(f"stdout exceeds {MAX_STDOUT_BYTES} bytes ({len(stdout)})")
        return None, errors

    if not stdout:
        if expect_success:
            errors.append("stdout empty on success")
        return None, errors

    text = stdout.decode("utf-8", errors="replace")
    # Exactly one JSON line: allow a single trailing newline, nothing else.
    if text.endswith("\n"):
        body = text[:-1]
    else:
        body = text
    if "\n" in body:
        errors.append("stdout has more than one line")
        return None, errors
    if not body.strip():
        if expect_success:
            errors.append("stdout empty on success")
        return None, errors
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        errors.append(f"stdout is not JSON: {exc}")
        return None, errors
    return value, errors


def run_tool_inputs(
    plugin_name: str,
    entry: dict[str, Any],
    home: Path,
    report: Report,
) -> None:
    name = entry["name"]
    fields = entry.get("fields") or {}
    exec_str = fields.get("exec")
    report.section(f"\n[{plugin_name}] tool {name}")

    if not exec_str:
        report.fail(f"{name}: missing fields.exec")
        return

    timeout = parse_timeout(fields.get("timeout"))
    if timeout is None:
        report.fail(f"{name}: missing or invalid fields.timeout (got {fields.get('timeout')!r})")
        return

    if fields.get("io_mode") not in ("json", "JSON"):
        report.fail(f"{name}: io_mode must be json (got {fields.get('io_mode')!r})")
        return

    script = exec_script_path(exec_str, home)
    if script is not None and not script.is_file():
        report.skip_ni(f"{name}: exec target not found ({script})")
        return

    schema_path = SCHEMAS_DIR / f"{name}.schema.json"
    schema = None
    if schema_path.is_file():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    else:
        report.fail(f"{name}: missing schema {schema_path}")

    input_dir = INPUTS_DIR / name
    if not input_dir.is_dir():
        report.fail(f"{name}: missing inputs directory {input_dir}")
        return

    cases = sorted(input_dir.glob("*"))
    if not cases:
        report.fail(f"{name}: no input cases in {input_dir}")
        return

    for case_path in cases:
        if case_path.name.startswith("."):
            continue
        stdin, meta = load_input_case(case_path)
        label = f"{name}/{case_path.name}"
        expect = meta.get("expect", "success")
        expect_success = expect == "success"

        # Oversized input: generate here if marked
        if meta.get("reason") == "input_too_large":
            stdin = (json.dumps({"root_path": "/tmp", "pad": "x" * (MAX_STDOUT_BYTES + 1)}) + "\n").encode()

        try:
            first = run_once(exec_str, stdin, timeout + 1.0, home)
        except subprocess.TimeoutExpired:
            report.fail(f"{label}: killed after timeout ({timeout}s)")
            continue

        wall = None  # reserved for future perf; L2 only enforces kill

        out_val, out_errs = check_stdout_contract(first.stdout, expect_success)
        for err in out_errs:
            report.fail(f"{label}: {err}")

        if expect_success:
            if first.returncode != 0:
                report.fail(
                    f"{label}: expected exit 0, got {first.returncode}; "
                    f"stderr={first.stderr[:500]!r}"
                )
                continue
            if out_val is None:
                continue
            if schema is not None:
                for err in validate_schema(out_val, schema):
                    report.fail(f"{label}: schema: {err}")
            # Determinism: second run
            try:
                second = run_once(exec_str, stdin, timeout + 1.0, home)
            except subprocess.TimeoutExpired:
                report.fail(f"{label}: second run timed out")
                continue
            if second.returncode != first.returncode:
                report.fail(f"{label}: non-deterministic exit code")
                continue
            v2, errs2 = check_stdout_contract(second.stdout, True)
            for err in errs2:
                report.fail(f"{label}: second run: {err}")
            if out_val is not None and v2 is not None:
                if strip_for_determinism(out_val) != strip_for_determinism(v2):
                    report.fail(f"{label}: non-deterministic stdout (after ignoring cached)")
                else:
                    report.ok(f"{label}")
            elif not out_errs and not errs2:
                report.ok(f"{label}")
        else:
            # Error path
            if first.returncode == 0:
                report.fail(f"{label}: expected non-zero exit, got 0")
                continue
            # No partial JSON object: if stdout present, must be one full JSON value
            if first.stdout:
                _, err_out = check_stdout_contract(first.stdout, expect_success=False)
                # allow single JSON error object; reject multi-line / partial
                if err_out and any("more than one line" in e or "not JSON" in e for e in err_out):
                    for err in err_out:
                        report.fail(f"{label}: {err}")
                    continue
            report.ok(f"{label} (error path)")


def main() -> int:
    parser = argparse.ArgumentParser(description="L2 JSON I/O contract tests")
    parser.add_argument("plugin", help="plugin directory name under plugins/")
    parser.add_argument(
        "--use-repo-tools",
        action="store_true",
        help="symlink tools/<plugin> into a temp HOME so ~/.config/naitv-mcp/tools/... resolves",
    )
    args = parser.parse_args()

    report = Report()
    plugin = load_plugin(args.plugin)
    entries = tool_entries(plugin)
    if not entries:
        report.fail(f"{args.plugin}: no kind=tool entries")
        report.dump()
        return 1

    with tempfile.TemporaryDirectory(prefix="naitv-contract-") as tmp:
        home = Path(tmp)
        if args.use_repo_tools:
            linked = prepare_home(args.plugin, home)
            if linked is None:
                report.section(
                    f"note: tools/{args.plugin} not in repo; cannot --use-repo-tools"
                )
        for entry in entries:
            run_tool_inputs(args.plugin, entry, home, report)

    report.dump()
    # not-implemented does not fail the harness hard alone if that is the only
    # outcome — still exit non-zero so CI notices missing tools; scripts/test.sh
    # treats this as expected for draft plugins.
    if report.failures:
        return 1
    if report.not_implemented and report.passed == 0:
        return 2  # distinct code: only not-implemented
    if report.not_implemented:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
