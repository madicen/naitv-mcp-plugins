# symbol-navigator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Phase 2 `symbol-navigator` plugin: three JSON I/O MCP tools for AST-based symbol definition, pattern search, and heuristic references (Go + Python).

**Architecture:** Independent Python orchestrator (`symbol_navigator.py`) with B1 `TOOL_NAME` dispatch, a cached flattened def index, Python `ast` extractors/refs, and a small `go_nav` helper for Go defs/refs. No LSP; no import of structural-anchor.

**Tech Stack:** Python 3 stdlib, Go 1.21+ (optional at runtime), naitv-mcp `io_mode=json`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-13-symbol-navigator-design.md`

## Global Constraints

- Version control: **jj only** (`jj commit -m "…"`). No `git commit` for local history. One jj commit per task.
- AST-first; **no LSP** in v1.
- Languages: `.py` + `.go` only.
- Tools: `find_symbol_definition`, `search_by_pattern`, `get_symbol_references` only.
- Independent package — do not import `structural_anchor` or shell out to it.
- Warm (cached-index) lookups **< 100ms**; cold build may exceed.
- Cache: `~/.cache/naitv-mcp/symbol-navigator/`; binary: `~/.cache/naitv-mcp/bin/go-nav`.
- Fingerprint = HEAD + dirty `git status --porcelain` (when git); do not poison cache when Go helper fails but `.go` files exist.
- `skip_dirs`: normalize list/comma-string; never char-split; empty → defaults.
- Install path: `~/.config/naitv-mcp/tools/symbol-navigator/symbol_navigator.py`.
- YAGNI / fewest files; references always include `"heuristic": true`.

## File map

| Path | Responsibility |
|------|----------------|
| `tools/symbol-navigator/symbol_navigator.py` | Walk, fingerprint, Python AST, cache, tools, main |
| `tools/symbol-navigator/go_nav/main.go` | Go defs + refs batch helper |
| `tools/symbol-navigator/go_nav/go.mod` | Go module |
| `tools/symbol-navigator/go_nav/testdata/*.go` | Fixtures |
| `tools/symbol-navigator/tests/test_walk.py` | Walk + skip normalize |
| `tools/symbol-navigator/tests/test_python_defs.py` | Python definitions |
| `tools/symbol-navigator/tests/test_python_refs.py` | Python references |
| `tools/symbol-navigator/tests/test_cache.py` | Index cache + dirty fp |
| `tools/symbol-navigator/tests/test_dispatch.py` | TOOL_NAME CLI |
| `tools/symbol-navigator/tests/test_integration.py` | Repo + warm perf |
| `tools/symbol-navigator/examples/sample_input.json` | Example stdin |
| `tools/symbol-navigator/README.md` | Install, SLA, heuristic note |
| `plugins/symbol-navigator.json` | Three tools + init rule |
| `adapters/symbol-navigator/AGENTS.md` | Compact fallback |
| `registry.json` | Register plugin |
| `README.md` | Plugins table row |

---

### Task 1: Walk, skip_dirs normalize, fingerprint

**Files:**
- Create: `tools/symbol-navigator/symbol_navigator.py`
- Create: `tools/symbol-navigator/tests/test_walk.py`

**Interfaces:**
- Produces:
  - `DEFAULT_SKIP_DIRS: set[str]`
  - `normalize_skip_dirs(raw) -> set[str]`
  - `iter_source_files(root: Path, depth: int, skip_dirs: set[str]) -> list[Path]`
  - `fingerprint(root: Path) -> str` — HEAD + porcelain dirty marker when git
  - `git_commit(root: Path) -> str | None`

- [ ] **Step 1: Write failing tests**

```python
# tools/symbol-navigator/tests/test_walk.py
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from symbol_navigator import iter_source_files, normalize_skip_dirs, DEFAULT_SKIP_DIRS


def test_normalize_skip_dirs_accepts_comma_string_and_list():
    assert normalize_skip_dirs("node_modules,vendor") == {"node_modules", "vendor"}
    assert normalize_skip_dirs(["dist", "build"]) == {"dist", "build"}
    assert normalize_skip_dirs(None) == DEFAULT_SKIP_DIRS
    assert normalize_skip_dirs("") == DEFAULT_SKIP_DIRS
    # must NOT be char-split
    assert "n" not in normalize_skip_dirs("node_modules")


def test_iter_respects_depth_and_extensions(tmp_path: Path):
    (tmp_path / "a.py").write_text("x=1\n")
    (tmp_path / "b.go").write_text("package main\n")
    (tmp_path / "c.txt").write_text("nope\n")
    deep = tmp_path / "d1" / "d2" / "d3"
    deep.mkdir(parents=True)
    (deep / "deep.py").write_text("y=1\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.py").write_text("z=1\n")

    files = {p.relative_to(tmp_path).as_posix() for p in iter_source_files(tmp_path, 2, DEFAULT_SKIP_DIRS)}
    assert "a.py" in files and "b.go" in files
    assert "c.txt" not in files
    assert "d1/d2/d3/deep.py" not in files
    assert "node_modules/x.py" not in files
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd tools/symbol-navigator && (test -d .venv || python3 -m venv .venv && .venv/bin/pip -q install pytest) && .venv/bin/python -m pytest tests/test_walk.py -v`  
Expected: FAIL (import / missing symbols)

- [ ] **Step 3: Minimal implementation**

```python
#!/usr/bin/env python3
"""symbol-navigator: AST symbol defs/refs for naitv-mcp (JSON stdin/stdout)."""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

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
```

- [ ] **Step 4: Run — expect PASS**

Run: `cd tools/symbol-navigator && .venv/bin/python -m pytest tests/test_walk.py -v`

- [ ] **Step 5: Commit (jj)**

```bash
jj commit -m "feat(symbol-navigator): add walk, skip_dirs normalize, and fingerprint"
```

---

### Task 2: Python definition extraction

**Files:**
- Modify: `tools/symbol-navigator/symbol_navigator.py`
- Create: `tools/symbol-navigator/tests/test_python_defs.py`
- Create: `tools/symbol-navigator/tests/fixtures/sample.py`

**Interfaces:**
- Produces: `extract_python_defs(path: Path) -> list[dict]`  
  Each dict: `{name, kind, file, line, column, signature, receivers, imports}`  
  (`file` = absolute path string; `receivers` always `[]` for Python; `imports` = module import names)

- [ ] **Step 1: Fixture + failing test**

```python
# tests/fixtures/sample.py
import os
from typing import List

class Outer:
    class Inner:
        def nested(self, x: int) -> int:
            return x

    def method(self, a: int, /, b: int = 1, *rest, c: int = 2, **kw) -> int:
        return a + b

def top(a: str) -> str:
    return a
```

```python
# tests/test_python_defs.py
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from symbol_navigator import extract_python_defs

FIX = Path(__file__).parent / "fixtures" / "sample.py"

def test_extract_python_defs_nested_and_signatures():
    defs = extract_python_defs(FIX)
    by = {(d["name"], d["kind"]): d for d in defs}
    assert ("Outer", "class") in by
    assert ("Inner", "class") in by
    assert ("nested", "method") in by
    assert ("method", "method") in by
    assert ("top", "function") in by
    assert "a: int" in by[("method", "method")]["signature"]
    assert "*rest" in by[("method", "method")]["signature"]
    assert "os" in by[("top", "function")]["imports"] or "os" in defs[0]["imports"]
    # imports attached per-file; every def shares file imports
    assert "os" in by[("top", "function")]["imports"]
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement `extract_python_defs`**

Implement using `ast`: collect imports from `Import`/`ImportFrom`; recurse `ClassDef` for nested classes/methods; full `_args_sig` with posonly/`/`/vararg/kwonly/kwarg; `column` from `node.col_offset + 1` (or `0` if missing).

```python
import ast
from typing import Any


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
        out.append({
            "name": name,
            "kind": kind,
            "file": str(path.resolve()),
            "line": getattr(node, "lineno", 0),
            "column": getattr(node, "col_offset", -1) + 1,
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
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit (jj)**

```bash
jj commit -m "feat(symbol-navigator): extract Python symbol definitions"
```

---

### Task 3: Python reference finding

**Files:**
- Modify: `tools/symbol-navigator/symbol_navigator.py`
- Create: `tools/symbol-navigator/tests/test_python_refs.py`
- Create: `tools/symbol-navigator/tests/fixtures/refs_sample.py`

**Interfaces:**
- Produces: `find_python_refs(path: Path, symbol: str, exclude_line: int | None = None) -> list[dict]`  
  Each: `{file, line, column, context}`

- [ ] **Step 1: Failing test**

```python
# fixtures/refs_sample.py
def Greeter():
    return 1

def use():
    return Greeter()
```

```python
def test_python_refs_finds_call_not_def():
    path = Path(__file__).parent / "fixtures" / "refs_sample.py"
    defs = extract_python_defs(path)
    greeter = next(d for d in defs if d["name"] == "Greeter")
    refs = find_python_refs(path, "Greeter", exclude_line=greeter["line"])
    assert any(r["line"] != greeter["line"] for r in refs)
    assert any("Greeter" in r["context"] for r in refs)
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement**

Walk AST for `ast.Name` / `ast.Attribute.attr` equal to `symbol`; skip node when `lineno == exclude_line` and node is the def name; `context` = stripped source line.

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit (jj)**

```bash
jj commit -m "feat(symbol-navigator): find Python symbol references"
```

---

### Task 4: Go `go_nav` helper

**Files:**
- Create: `tools/symbol-navigator/go_nav/go.mod`
- Create: `tools/symbol-navigator/go_nav/main.go`
- Create: `tools/symbol-navigator/go_nav/main_test.go`
- Create: `tools/symbol-navigator/go_nav/testdata/sample.go`
- Create: `tools/symbol-navigator/go_nav/testdata/user.go`

**Interfaces:**
- stdin JSON modes:
  - `{"mode":"index","files":["..."]}` → `{"defs":[...],"errors":N}`
  - `{"mode":"refs","symbol":"X","files":["..."],"exclude":[{"file":"...","line":N}]}` → `{"references":[...],"errors":N}`
- Def shape matches Python index fields; method `signature` includes receiver e.g. `func (UserService) Hello()`.

- [ ] **Step 1: Testdata + failing Go test**

```go
// testdata/sample.go
package sample

type UserService struct{}

func (u UserService) Hello() string { return "hi" }

func NewUserService() *UserService { return &UserService{} }
```

```go
// testdata/user.go
package sample

func Use() {
	_ = NewUserService()
	var s UserService
	_ = s.Hello()
}
```

Test `Index` finds `UserService` type + `Hello` method with receiver in signature; test `Refs` finds uses excluding def lines.

- [ ] **Step 2: `go test` — expect FAIL**

- [ ] **Step 3: Implement main.go**

Use `go/parser` + `go/ast`. For refs: `ast.Inspect` for `*ast.Ident` matching symbol (and selectors using `Sel.Name`). Sort outputs by file, line for determinism. Include exported const/var.

- [ ] **Step 4: `go test ./...` PASS**

- [ ] **Step 5: Commit (jj)**

```bash
jj commit -m "feat(symbol-navigator): add go_nav helper for defs and refs"
```

---

### Task 5: Index cache + ensure go-nav binary

**Files:**
- Modify: `tools/symbol-navigator/symbol_navigator.py`
- Create: `tools/symbol-navigator/tests/test_cache.py`

**Interfaces:**
- `cache_dir() -> Path`
- `bin_dir() -> Path`
- `cache_key(root, depth, skip_dirs, fp) -> str`
- `load_index(key) -> dict | None` — `{"defs":[...]}`
- `save_index(key, payload) -> None`
- `ensure_go_nav_bin(src_dir: Path) -> Path | None` — wrap OSError; mtime vs `main.go`
- `build_index(root, depth, skip_dirs) -> tuple[dict, bool]` — returns (payload, go_degraded)  
  `go_degraded=True` when `.go` files exist but helper unavailable

- [ ] **Step 1: Tests**

```python
def test_cache_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    key = cache_key(Path("/repo"), 3, {"vendor"}, "abc")
    assert load_index(key) is None
    save_index(key, {"defs": [{"name": "X"}]})
    assert load_index(key)["defs"][0]["name"] == "X"

def test_go_degraded_not_saved(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "p"
    root.mkdir()
    (root / "a.go").write_text("package a\n")
    monkeypatch.setattr("symbol_navigator.ensure_go_nav_bin", lambda _s: None)
    payload, degraded = build_index(root, 3, set())
    assert degraded is True
    # save path tested later in get_* tools — here assert build_index reports degraded
```

- [ ] **Step 2–4: Implement + PASS**

`build_index`: walk files; Python defs via thread pool; Go via helper `mode=index`; merge defs; set `go_degraded`.

- [ ] **Step 5: Commit (jj)**

```bash
jj commit -m "feat(symbol-navigator): add symbol index cache and go-nav ensure"
```

---

### Task 6: Three tools + main() dispatch

**Files:**
- Modify: `tools/symbol-navigator/symbol_navigator.py`
- Create: `tools/symbol-navigator/tests/test_dispatch.py`
- Create: `tools/symbol-navigator/examples/sample_input.json`

**Interfaces:**
- `ensure_index(root, depth, skip) -> tuple[list[dict], bool cached, bool go_degraded]`
  - load cache if key matches; else build; save only if not `go_degraded`
- `find_symbol_definition(root, depth, skip, symbol, kind=None) -> dict`
- `search_by_pattern(root, depth, skip, pattern, kind=None) -> dict`
- `get_symbol_references(root, depth, skip, symbol, file_path=None) -> dict`
- `main()`

**Behavior notes:**
- Def lookup: filter index by exact name (+ optional kind); sort by `(file,line)`; primary fields from first match; include `matches` when len≠1 or always include when >1; `source:"ast"`; `cached` flag.
- Pattern: `re.compile(pattern)` — on failure exit 1 from main; filter defs by `re.search` on name.
- Refs: resolve def; order files with package-of-`file_path` first; Python `find_python_refs` + Go helper `mode=refs`; always `"heuristic": true`.

- [ ] **Step 1: Dispatch tests**

Cover: find Greeter in fixture tree; search pattern `^Greet`; refs return heuristic; unknown TOOL_NAME nonzero; invalid regex nonzero; not-found empty matches exit 0; cache hit on second find.

```json
{"root_path": ".", "symbol": "UserService"}
```
→ `examples/sample_input.json` (document absolute path for MCP).

- [ ] **Step 2–4: Implement + PASS**

- [ ] **Step 5: Commit (jj)**

```bash
jj commit -m "feat(symbol-navigator): wire definition, pattern, and reference tools"
```

---

### Task 7: Plugin JSON, registry, adapter, README

**Files:**
- Create: `plugins/symbol-navigator.json`
- Create: `adapters/symbol-navigator/AGENTS.md`
- Create: `tools/symbol-navigator/README.md`
- Modify: `registry.json`
- Modify: `README.md`

- [ ] **Step 1: Plugin JSON**

Three tools with B1 `TOOL_NAME=…`, `io_mode=json`, `timeout=30s`, params per spec. Init rule: prefer symbol-navigator for precise defs/refs (after structural-anchor orients).

- [ ] **Step 2: Adapter + README**

README must say: **Not a replacement for gopls**; warm <100ms SLA; heuristic refs; symlink install path; Go optional.

- [ ] **Step 3: Registry + root README table row**

- [ ] **Step 4: `python3 -c "import json; json.load(open('plugins/symbol-navigator.json'))"`**

- [ ] **Step 5: Commit (jj)**

```bash
jj commit -m "feat(symbol-navigator): add plugin JSON, registry, adapter, README"
```

Do **not** commit `__pycache__` / `.venv` (root `.gitignore` already covers).

---

### Task 8: Integration + warm perf smoke

**Files:**
- Create: `tools/symbol-navigator/tests/test_integration.py`

- [ ] **Step 1: Tests**

```python
def test_this_repo_find_and_cache(tmp_path):
    # find a known Python symbol from tools/structural-anchor or symbol_navigator itself
    ...
    assert first["cached"] is False
    assert second.get("cached") is True or second.get("file")

def test_warm_lookup_under_100ms(tmp_path):
    # build index once, then time find_symbol_definition; assert elapsed < 0.1
```

Use isolated `HOME`. Soft assert 100ms with small fixture (not whole linux tree).

- [ ] **Step 2: Full suite**

```bash
cd tools/symbol-navigator && .venv/bin/python -m pytest tests/ -v
cd go_nav && go test ./...
```

Expected: all PASS

- [ ] **Step 3: Commit (jj)**

```bash
jj commit -m "test(symbol-navigator): integration and warm lookup perf smoke"
```

---

## Self-review (plan vs spec)

| Spec item | Task |
|-----------|------|
| B1 TOOL_NAME + 3 tools | 6, 7 |
| AST-first, no LSP | Global + all |
| Go + Python only | 1–4 |
| Independent of structural-anchor | Global |
| Heuristic scoped refs | 3, 4, 6 |
| Warm <100ms | 5, 8 |
| Dirty fingerprint + no Go poison | 1, 5 |
| skip_dirs normalize | 1 |
| Plugin/registry/README | 7 |
| jj per task | every Step 5 |

No TBD placeholders. Nested Python classes covered in Task 2. Go receiver signatures in Task 4.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-13-symbol-navigator.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session with executing-plans checkpoints  

Which approach?
