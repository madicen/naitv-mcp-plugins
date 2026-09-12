#!/usr/bin/env python3
"""structural-anchor: codebase map for naitv-mcp (JSON stdin/stdout)."""
from __future__ import annotations

import ast
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_SKIP_DIRS = {
    "node_modules",
    ".git",
    "vendor",
    ".venv",
    "dist",
    "build",
    "__pycache__",
}
SOURCE_EXTS = {".py", ".go"}


def iter_source_files(root: Path, depth: int, skip_dirs: set[str]) -> list[Path]:
    """Walk root; root is depth 0; do not descend past `depth`."""
    root = root.resolve()
    out: list[Path] = []

    def walk(dir_path: Path, d: int) -> None:
        try:
            with os.scandir(dir_path) as it:
                for ent in it:
                    name = ent.name
                    if ent.is_dir(follow_symlinks=False):
                        if name in skip_dirs or name.startswith("."):
                            continue
                        if d + 1 > depth:
                            continue
                        walk(Path(ent.path), d + 1)
                    elif ent.is_file(follow_symlinks=False):
                        if Path(name).suffix in SOURCE_EXTS:
                            out.append(Path(ent.path))
        except OSError:
            return

    walk(root, 0)
    return out


def git_commit(root: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if r.returncode == 0:
            return r.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None


def fingerprint(root: Path) -> str:
    commit = git_commit(root)
    if commit:
        return commit
    index = root / ".git" / "index"
    if index.is_file():
        return f"index:{index.stat().st_mtime_ns}"
    h = hashlib.sha256()
    try:
        for ent in sorted(os.scandir(root), key=lambda e: e.name):
            h.update(ent.name.encode())
            try:
                h.update(str(ent.stat(follow_symlinks=False).st_mtime_ns).encode())
            except OSError:
                pass
    except OSError:
        h.update(b"empty")
    return f"top:{h.hexdigest()[:16]}"


def cache_dir() -> Path:
    return Path.home() / ".cache" / "naitv-mcp" / "structural-anchor"


def bin_dir() -> Path:
    return Path.home() / ".cache" / "naitv-mcp" / "bin"


def cache_key(root: Path, depth: int, skip_dirs: set[str], fp: str) -> str:
    raw = f"{root.resolve()}|{depth}|{','.join(sorted(skip_dirs))}|{fp}"
    return hashlib.sha256(raw.encode()).hexdigest()


def load_cache(key: str) -> dict[str, Any] | None:
    p = cache_dir() / f"{key}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_cache(key: str, payload: dict[str, Any]) -> None:
    d = cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps(payload), encoding="utf-8")


def ensure_go_symbols_bin(src_dir: Path) -> Path | None:
    """Build go_symbols into cache bin if needed. None if go unavailable."""
    out = bin_dir() / "go-symbols"
    main_go = src_dir / "main.go"
    if not main_go.is_file():
        return None
    need = True
    if out.is_file():
        need = out.stat().st_mtime_ns < main_go.stat().st_mtime_ns
    if not need:
        return out
    bin_dir().mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(
            ["go", "build", "-o", str(out), "."],
            cwd=src_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return out if out.is_file() else None


def cyclomatic_python(node: ast.AST) -> float:
    decisions = 0
    for n in ast.walk(node):
        if isinstance(n, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With, ast.Assert)):
            decisions += 1
        elif isinstance(n, ast.BoolOp):
            decisions += max(0, len(n.values) - 1)
        elif isinstance(n, ast.comprehension):
            decisions += 1
    return float(decisions + 1)


def _ann(a: ast.expr | None) -> str:
    if a is None:
        return ""
    try:
        return ast.unparse(a)
    except Exception:
        return ""


def _args_sig(args: ast.arguments) -> str:
    parts: list[str] = []
    for a in args.args:
        ann = _ann(a.annotation)
        parts.append(f"{a.arg}: {ann}" if ann else a.arg)
    return ", ".join(parts)


def extract_python_symbols(path: Path) -> tuple[list[dict[str, Any]], list[float], int]:
    src = path.read_text(encoding="utf-8", errors="replace")
    lines = src.count("\n") + (0 if src.endswith("\n") or not src else 1)
    tree = ast.parse(src, filename=str(path))
    symbols: list[dict[str, Any]] = []
    complexities: list[float] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            symbols.append(
                {
                    "name": node.name,
                    "kind": "class",
                    "signature": f"class {node.name}",
                    "line": node.lineno,
                }
            )
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    prefix = "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                    ret = _ann(item.returns)
                    sig = f"{prefix} {item.name}({_args_sig(item.args)})"
                    if ret:
                        sig += f" -> {ret}"
                    symbols.append(
                        {"name": item.name, "kind": "method", "signature": sig, "line": item.lineno}
                    )
                    complexities.append(cyclomatic_python(item))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            ret = _ann(node.returns)
            sig = f"{prefix} {node.name}({_args_sig(node.args)})"
            if ret:
                sig += f" -> {ret}"
            symbols.append(
                {"name": node.name, "kind": "function", "signature": sig, "line": node.lineno}
            )
            complexities.append(cyclomatic_python(node))
    return symbols, complexities, lines


def build_project_map(root: Path, depth: int, skip_dirs: set[str]) -> dict[str, Any]:
    root = root.resolve()
    files = sorted(iter_source_files(root, depth, skip_dirs))
    python_files = [path for path in files if path.suffix == ".py"]
    go_files = [path for path in files if path.suffix == ".go"]
    packages: dict[str, dict[str, Any]] = {}
    complexities: dict[str, list[float]] = {"python": [], "go": []}
    line_counts = {"python": 0, "go": 0}
    parse_errors = 0

    def add_python(result: tuple[Path, tuple[list[dict[str, Any]], list[float], int] | Exception]) -> None:
        nonlocal parse_errors
        path, extracted = result
        if isinstance(extracted, Exception):
            parse_errors += 1
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
                line_counts["python"] += source.count("\n") + (
                    0 if source.endswith("\n") or not source else 1
                )
            except OSError:
                pass
            return
        symbols, function_complexity, lines = extracted
        relative_parent = path.parent.relative_to(root)
        package_path = relative_parent.as_posix() if relative_parent.parts else "."
        if package_path == ".":
            key = f"python:{path.relative_to(root).as_posix()}"
            name = path.stem
        else:
            key = f"python:{package_path}"
            name = path.parent.name
        package = packages.setdefault(
            key, {"name": name, "path": package_path, "symbols": []}
        )
        package["symbols"].extend(symbols)
        complexities["python"].extend(function_complexity)
        line_counts["python"] += lines

    def extract(path: Path) -> tuple[Path, tuple[list[dict[str, Any]], list[float], int] | Exception]:
        try:
            return path, extract_python_symbols(path)
        except (OSError, SyntaxError) as exc:
            return path, exc

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for result in executor.map(extract, python_files):
            add_python(result)

    for path in go_files:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            line_counts["go"] += source.count("\n") + (
                0 if source.endswith("\n") or not source else 1
            )
        except OSError:
            parse_errors += 1

    if go_files:
        go_bin = ensure_go_symbols_bin(Path(__file__).parent / "go_symbols")
        if go_bin is None:
            print("warning: Go symbols unavailable", file=sys.stderr)
        else:
            try:
                proc = subprocess.run(
                    [str(go_bin)],
                    input=json.dumps({"files": [str(path) for path in go_files]}),
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
                if proc.returncode != 0:
                    raise RuntimeError(proc.stderr.strip() or "go-symbols failed")
                result = json.loads(proc.stdout)
                parse_errors += int(result.get("errors", 0))
                complexities["go"].extend(result.get("func_complexity", []))
                for go_package in sorted(
                    result.get("packages", []), key=lambda package: package["path"]
                ):
                    package_dir = Path(go_package["path"])
                    try:
                        package_path = package_dir.relative_to(root).as_posix() or "."
                    except ValueError:
                        package_path = package_dir.as_posix()
                    key = f"go:{package_path}"
                    package = packages.setdefault(
                        key,
                        {
                            "name": go_package["name"],
                            "path": package_path,
                            "symbols": [],
                        },
                    )
                    package["symbols"].extend(go_package.get("symbols", []))
            except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, RuntimeError) as exc:
                print(f"warning: Go symbols unavailable: {exc}", file=sys.stderr)

    by_language: dict[str, dict[str, float | int]] = {}
    file_counts = {"python": len(python_files), "go": len(go_files)}
    for language in sorted(language for language, count in file_counts.items() if count):
        values = complexities[language]
        by_language[language] = {
            "files": file_counts[language],
            "lines": line_counts[language],
            "complexity": sum(values) / len(values) if values else 0,
        }
    all_complexities = complexities["python"] + complexities["go"]
    payload: dict[str, Any] = {
        "packages": sorted(packages.values(), key=lambda package: (package["path"], package["name"])),
        "languages": sorted(by_language),
        "statistics": {
            "total_files": len(files),
            "total_lines": sum(line_counts.values()),
            "complexity": (
                sum(all_complexities) / len(all_complexities) if all_complexities else 0
            ),
            "packages": len(packages),
            "parse_errors": parse_errors,
            "by_language": by_language,
        },
    }
    commit = git_commit(root)
    if commit:
        payload["commit"] = commit
    return payload


def get_project_map(root: Path, depth: int, skip_dirs: set[str]) -> dict[str, Any]:
    root = root.resolve()
    key = cache_key(root, depth, skip_dirs, fingerprint(root))
    payload = load_cache(key)
    cached = payload is not None
    if payload is None:
        payload = build_project_map(root, depth, skip_dirs)
        save_cache(key, payload)
    return {**payload, "cached": cached}


def list_languages(root: Path, depth: int, skip_dirs: set[str]) -> dict[str, Any]:
    project_map = get_project_map(root, depth, skip_dirs)
    by_language = project_map["statistics"]["by_language"]
    languages = [
        {
            "id": language,
            "file_count": by_language[language]["files"],
            "line_count": by_language[language]["lines"],
        }
        for language in sorted(by_language)
    ]
    result: dict[str, Any] = {
        "languages": languages,
        "primary": max(languages, key=lambda item: item["file_count"])["id"]
        if languages
        else None,
        "cached": project_map["cached"],
    }
    if "commit" in project_map:
        result["commit"] = project_map["commit"]
    return result


def get_codebase_statistics(root: Path, depth: int, skip_dirs: set[str]) -> dict[str, Any]:
    project_map = get_project_map(root, depth, skip_dirs)
    result = {**project_map["statistics"], "cached": project_map["cached"]}
    if "commit" in project_map:
        result["commit"] = project_map["commit"]
    return result


def main() -> None:
    tool = os.environ.get("TOOL_NAME", "").strip()
    try:
        data = json.loads(sys.stdin.readline())
    except Exception as exc:
        print(f"invalid JSON: {exc}", file=sys.stderr)
        sys.exit(1)
    root = data.get("root_path")
    if not root:
        print("root_path required", file=sys.stderr)
        sys.exit(1)
    depth = int(data.get("depth", 3))
    skip = set(data.get("skip_dirs") or DEFAULT_SKIP_DIRS)
    handlers = {
        "get_project_map": get_project_map,
        "list_languages": list_languages,
        "get_codebase_statistics": get_codebase_statistics,
    }
    if tool not in handlers:
        print(f"unknown or missing TOOL_NAME: {tool!r}", file=sys.stderr)
        sys.exit(1)
    result = handlers[tool](Path(root), depth, skip)
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
