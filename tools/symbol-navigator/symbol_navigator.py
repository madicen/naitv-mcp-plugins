#!/usr/bin/env python3
"""symbol-navigator: AST symbol defs/refs for naitv-mcp (JSON stdin/stdout)."""
from __future__ import annotations

import ast
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_SKIP_DIRS = {
    "node_modules", ".git", "vendor", ".venv", "dist", "build", "__pycache__",
}
SOURCE_EXTS = {".py", ".go"}


def normalize_skip_dirs(raw) -> set[str]:
    if raw is None or raw == "":
        return set(DEFAULT_SKIP_DIRS)
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("[") and s.endswith("]"):
            import json
            try:
                raw = json.loads(s)
            except json.JSONDecodeError:
                raw = [p.strip() for p in s.split(",") if p.strip()]
            else:
                pass
        else:
            raw = [p.strip() for p in s.split(",") if p.strip()]
    if isinstance(raw, (list, tuple, set)):
        out = {str(x).strip() for x in raw if str(x).strip()}
        return out or set(DEFAULT_SKIP_DIRS)
    return set(DEFAULT_SKIP_DIRS)


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
            cwd=root, capture_output=True, text=True, timeout=5, check=False,
        )
        if r.returncode == 0:
            return r.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None


def _git_dirty(root: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root, capture_output=True, text=True, timeout=5, check=False,
        )
        if r.returncode == 0 and r.stdout.strip():
            return hashlib.sha256(r.stdout.encode()).hexdigest()[:16]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def fingerprint(root: Path) -> str:
    commit = git_commit(root)
    if commit:
        dirty = _git_dirty(root)
        return f"{commit}:dirty:{dirty}" if dirty else commit
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
    return Path.home() / ".cache" / "naitv-mcp" / "symbol-navigator"


def bin_dir() -> Path:
    return Path.home() / ".cache" / "naitv-mcp" / "bin"


def cache_key(root: Path, depth: int, skip_dirs: set[str], fp: str) -> str:
    raw = f"{root.resolve()}|{depth}|{','.join(sorted(skip_dirs))}|{fp}"
    return hashlib.sha256(raw.encode()).hexdigest()


def load_index(key: str) -> dict[str, Any] | None:
    path = cache_dir() / f"{key}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_index(key: str, payload: dict[str, Any]) -> None:
    directory = cache_dir()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{key}.json").write_text(json.dumps(payload), encoding="utf-8")


def ensure_go_nav_bin(src_dir: Path) -> Path | None:
    """Build go_nav into the cache when stale; return None if unavailable."""
    try:
        output = bin_dir() / "go-nav"
        main_go = src_dir / "main.go"
        if not main_go.is_file():
            return None
        if output.is_file() and output.stat().st_mtime_ns >= main_go.stat().st_mtime_ns:
            return output
        output.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["go", "build", "-o", str(output), "."],
            cwd=src_dir,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return output if result.returncode == 0 and output.is_file() else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _ann(a: ast.expr | None) -> str:
    if a is None:
        return ""
    try:
        return ast.unparse(a)
    except Exception:
        return ""


def _args_sig(args: ast.arguments) -> str:
    parts: list[str] = []
    for a in args.posonlyargs:
        ann = _ann(a.annotation)
        parts.append(f"{a.arg}: {ann}" if ann else a.arg)
    if args.posonlyargs:
        parts.append("/")
    for a in args.args:
        ann = _ann(a.annotation)
        parts.append(f"{a.arg}: {ann}" if ann else a.arg)
    if args.vararg:
        parts.append("*" + args.vararg.arg)
    elif args.kwonlyargs:
        parts.append("*")
    for a in args.kwonlyargs:
        ann = _ann(a.annotation)
        parts.append(f"{a.arg}: {ann}" if ann else a.arg)
    if args.kwarg:
        parts.append("**" + args.kwarg.arg)
    return ", ".join(parts)


def _file_imports(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names.append(mod)
    return names


def extract_python_defs(path: Path) -> list[dict[str, Any]]:
    src = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src, filename=str(path))
    imports = _file_imports(tree)
    out: list[dict[str, Any]] = []

    def add(name, kind, node, signature):
        col = getattr(node, "col_offset", None)
        out.append({
            "name": name,
            "kind": kind,
            "file": str(path.resolve()),
            "line": getattr(node, "lineno", 0),
            "column": (col + 1) if col is not None else 0,
            "signature": signature,
            "receivers": [],
            "imports": list(imports),
        })

    def walk_body(body: list[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                add(node.name, "class", node, f"class {node.name}")
                for item in node.body:
                    if isinstance(item, ast.ClassDef):
                        walk_body([item])
                    elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        prefix = "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                        ret = _ann(item.returns)
                        sig = f"{prefix} {item.name}({_args_sig(item.args)})"
                        if ret:
                            sig += f" -> {ret}"
                        add(item.name, "method", item, sig)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                ret = _ann(node.returns)
                sig = f"{prefix} {node.name}({_args_sig(node.args)})"
                if ret:
                    sig += f" -> {ret}"
                add(node.name, "function", node, sig)

    walk_body(tree.body)
    return out


def _python_name_is_def_site(node: ast.AST, parents: dict[ast.AST, ast.AST], symbol: str) -> bool:
    if isinstance(node, ast.Name) and node.id == symbol:
        p = parents.get(node)
        if isinstance(p, ast.Assign):
            for t in p.targets:
                if t is node:
                    return True
        if isinstance(p, ast.AnnAssign) and p.target is node:
            return True
        if isinstance(p, ast.alias) and (p.asname == symbol or p.name.split(".")[-1] == symbol):
            return True
        if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return p.name == symbol
    if isinstance(node, ast.Attribute) and node.attr == symbol:
        p = parents.get(node)
        if isinstance(p, ast.Assign):
            for t in p.targets:
                if t is node:
                    return True
    return False


def find_python_refs(
    path: Path, symbol: str, exclude_line: int | None = None,
) -> list[dict[str, Any]]:
    src = path.read_text(encoding="utf-8", errors="replace")
    lines = src.splitlines()
    tree = ast.parse(src, filename=str(path))
    file_str = str(path.resolve())
    parents: dict[ast.AST, ast.AST] = {}

    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    out: list[dict[str, Any]] = []

    def maybe_add(node: ast.AST) -> None:
        lineno = getattr(node, "lineno", None)
        if lineno is None:
            return
        if exclude_line is not None and lineno == exclude_line:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == symbol:
                    return
            if _python_name_is_def_site(node, parents, symbol):
                return
        col = getattr(node, "col_offset", None)
        ctx = lines[lineno - 1].strip() if 1 <= lineno <= len(lines) else ""
        out.append({
            "file": file_str,
            "line": lineno,
            "column": (col + 1) if col is not None else 0,
            "context": ctx,
        })

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == symbol:
            maybe_add(node)
        elif isinstance(node, ast.Attribute) and node.attr == symbol:
            maybe_add(node)

    return out


def build_index(
    root: Path, depth: int, skip_dirs: set[str],
) -> tuple[dict[str, Any], bool]:
    files = sorted(iter_source_files(root, depth, skip_dirs))
    python_files = [path for path in files if path.suffix == ".py"]
    go_files = [path for path in files if path.suffix == ".go"]
    defs: list[dict[str, Any]] = []

    def extract(path: Path) -> list[dict[str, Any]]:
        try:
            return extract_python_defs(path)
        except (OSError, SyntaxError):
            return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for extracted in executor.map(extract, python_files):
            defs.extend(extracted)

    go_degraded = bool(go_files)
    if go_files:
        go_bin = ensure_go_nav_bin(Path(__file__).parent / "go_nav")
        if go_bin is None:
            print("warning: Go symbols unavailable", file=sys.stderr)
        else:
            try:
                result = subprocess.run(
                    [str(go_bin)],
                    input=json.dumps({
                        "mode": "index",
                        "files": [str(path) for path in go_files],
                    }),
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "go-nav failed")
                defs.extend(json.loads(result.stdout).get("defs", []))
                go_degraded = False
            except (
                OSError,
                subprocess.TimeoutExpired,
                json.JSONDecodeError,
                RuntimeError,
            ) as exc:
                print(f"warning: Go symbols unavailable: {exc}", file=sys.stderr)

    defs.sort(key=lambda item: (
        item.get("file", ""),
        item.get("line", 0),
        item.get("column", 0),
        item.get("name", ""),
    ))
    return {"defs": defs}, go_degraded


def ensure_index(
    root: Path, depth: int, skip_dirs: set[str],
) -> tuple[list[dict[str, Any]], bool, bool]:
    root = root.resolve()
    key = cache_key(root, depth, skip_dirs, fingerprint(root))
    payload = load_index(key)
    if payload is not None:
        return payload.get("defs", []), True, False

    payload, go_degraded = build_index(root, depth, skip_dirs)
    if not go_degraded:
        save_index(key, payload)
    return payload.get("defs", []), False, go_degraded


def _definition_result(definition: dict[str, Any]) -> dict[str, Any]:
    return {
        "file": definition.get("file", ""),
        "line": definition.get("line", 0),
        "column": definition.get("column", 0),
        "type": definition.get("kind", ""),
        "signature": definition.get("signature", ""),
        "receivers": definition.get("receivers", []),
        "imports": definition.get("imports", []),
        "source": "ast",
    }


def find_symbol_definition(
    root: Path,
    depth: int,
    skip_dirs: set[str],
    symbol: str,
    kind: str | None = None,
) -> dict[str, Any]:
    definitions, cached, _ = ensure_index(root, depth, skip_dirs)
    matches = [
        definition for definition in definitions
        if definition.get("name") == symbol
        and (kind is None or definition.get("kind") == kind)
    ]
    matches.sort(key=lambda item: (item.get("file", ""), item.get("line", 0)))
    if not matches:
        return {"matches": [], "cached": cached}

    result = {**_definition_result(matches[0]), "cached": cached}
    if len(matches) > 1:
        result["matches"] = [_definition_result(match) for match in matches]
    return result


def search_by_pattern(
    root: Path,
    depth: int,
    skip_dirs: set[str],
    pattern: str,
    kind: str | None = None,
) -> dict[str, Any]:
    regex = re.compile(pattern)
    definitions, cached, _ = ensure_index(root, depth, skip_dirs)
    results = [
        {
            "name": definition.get("name", ""),
            "kind": definition.get("kind", ""),
            "file": definition.get("file", ""),
            "line": definition.get("line", 0),
            "signature": definition.get("signature", ""),
        }
        for definition in definitions
        if regex.search(definition.get("name", ""))
        and (kind is None or definition.get("kind") == kind)
    ]
    results.sort(key=lambda item: (item["file"], item["line"], item["name"]))
    return {"results": results, "cached": cached}


def get_symbol_references(
    root: Path,
    depth: int,
    skip_dirs: set[str],
    symbol: str,
    file_path: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    definitions, cached, _ = ensure_index(root, depth, skip_dirs)
    matches = sorted(
        (definition for definition in definitions if definition.get("name") == symbol),
        key=lambda item: (item.get("file", ""), item.get("line", 0)),
    )
    if not matches:
        return {
            "definition": None,
            "references": [],
            "cached": cached,
            "heuristic": True,
        }

    files = iter_source_files(root, depth, skip_dirs)
    if file_path:
        hint = Path(file_path)
        if not hint.is_absolute():
            hint = root / hint
        package = hint.resolve().parent
        files.sort(key=lambda path: (
            path.resolve().parent != package,
            str(path.resolve()),
        ))
    else:
        files.sort(key=lambda path: str(path.resolve()))

    excluded = {
        (str(Path(definition.get("file", "")).resolve()), definition.get("line", 0))
        for definition in matches
    }
    references: list[dict[str, Any]] = []
    for path in (path for path in files if path.suffix == ".py"):
        try:
            references.extend(find_python_refs(path, symbol))
        except (OSError, SyntaxError):
            continue

    go_files = [path for path in files if path.suffix == ".go"]
    if go_files:
        go_bin = ensure_go_nav_bin(Path(__file__).parent / "go_nav")
        if go_bin is None:
            print("warning: Go references unavailable", file=sys.stderr)
        else:
            try:
                result = subprocess.run(
                    [str(go_bin)],
                    input=json.dumps({
                        "mode": "refs",
                        "symbol": symbol,
                        "files": [str(path) for path in go_files],
                        "exclude": [
                            {"file": definition.get("file", ""), "line": definition.get("line", 0)}
                            for definition in matches
                        ],
                    }),
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "go-nav failed")
                references.extend(json.loads(result.stdout).get("references", []))
            except (
                OSError,
                subprocess.TimeoutExpired,
                json.JSONDecodeError,
                RuntimeError,
            ) as exc:
                print(f"warning: Go references unavailable: {exc}", file=sys.stderr)

    references = [
        reference for reference in references
        if (str(Path(reference["file"]).resolve()), reference["line"]) not in excluded
    ]
    file_order = {str(path.resolve()): index for index, path in enumerate(files)}
    references.sort(key=lambda item: (
        file_order.get(str(Path(item["file"]).resolve()), len(file_order)),
        item["line"],
        item["column"],
    ))
    return {
        "definition": _definition_result(matches[0]),
        "references": references,
        "cached": cached,
        "heuristic": True,
    }


def main() -> None:
    tool = os.environ.get("TOOL_NAME", "").strip()
    handlers = {
        "find_symbol_definition": find_symbol_definition,
        "search_by_pattern": search_by_pattern,
        "get_symbol_references": get_symbol_references,
    }
    if tool not in handlers:
        print(f"unknown or missing TOOL_NAME: {tool!r}", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(sys.stdin.readline())
        root_path = data.get("root_path")
        if not root_path:
            raise ValueError("root_path required")
        depth = int(data.get("depth", 3))
        skip_dirs = normalize_skip_dirs(data.get("skip_dirs"))
        if tool == "search_by_pattern":
            pattern = data.get("pattern")
            if not isinstance(pattern, str):
                raise ValueError("pattern required")
            result = search_by_pattern(
                Path(root_path), depth, skip_dirs, pattern, data.get("kind"),
            )
        else:
            symbol = data.get("symbol")
            if not isinstance(symbol, str) or not symbol:
                raise ValueError("symbol required")
            if tool == "find_symbol_definition":
                result = find_symbol_definition(
                    Path(root_path), depth, skip_dirs, symbol, data.get("kind"),
                )
            else:
                result = get_symbol_references(
                    Path(root_path), depth, skip_dirs, symbol, data.get("file_path"),
                )
    except re.error as exc:
        print(f"invalid regex: {exc}", file=sys.stderr)
        sys.exit(1)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    json.dump(result, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
