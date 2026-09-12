# structural-anchor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Phase 2 `structural-anchor` plugin: three JSON I/O MCP tools that build a cached Python+Go symbol map of a codebase.

**Architecture:** One Python orchestrator (`structural_anchor.py`) dispatches on `TOOL_NAME`, walks a depth-limited tree, parses Python via `ast`, batches Go files into a small `go_symbols` helper (`go/parser`), and caches full maps under `~/.cache/naitv-mcp/`. Three plugin tool entries share that script via B1 `TOOL_NAME=…` in `exec`.

**Tech Stack:** Python 3 stdlib, Go 1.21+ (optional at runtime), naitv-mcp `io_mode=json` tool entries, `pytest` for tests.

**Spec:** `docs/superpowers/specs/2026-09-12-structural-anchor-design.md`

## Global Constraints

- Version control: use **jj only** (`jj commit -m "…"`). Do **not** use `git add` / `git commit` for local history. Each task ends with its own jj commit.
- Languages v1: `.py` + `.go` only; no tree-sitter; no TypeScript.
- Tools v1: `get_project_map`, `list_languages`, `get_codebase_statistics` only (no `validate_structure`).
- Depth = hard directory walk stop; AST nesting inside files is unlimited.
- `total_files` / `total_lines` count only `.py` and `.go` under the walk.
- Cache: `~/.cache/naitv-mcp/structural-anchor/`; Go binary: `~/.cache/naitv-mcp/bin/go-symbols`.
- Stdlib-only Python orchestrator (no pip deps for runtime).
- Install path for exec: `~/.config/naitv-mcp/tools/structural-anchor/structural_anchor.py` (document copy/symlink from repo).
- YAGNI / lazy-ladder: fewest files that work; one small test file per concern is enough.

## File map

| Path | Responsibility |
|------|----------------|
| `tools/structural-anchor/structural_anchor.py` | CLI, dispatch, walk, Python parse, cache, stats, Go helper invoke |
| `tools/structural-anchor/go_symbols/main.go` | Batch Go symbol extraction |
| `tools/structural-anchor/go_symbols/go.mod` | Go module |
| `tools/structural-anchor/go_symbols/testdata/sample.go` | Fixture for Go helper |
| `tools/structural-anchor/tests/test_walk.py` | Walk + prune + depth |
| `tools/structural-anchor/tests/test_python_symbols.py` | Python AST extract |
| `tools/structural-anchor/tests/test_cache.py` | Cache key / hit / miss |
| `tools/structural-anchor/tests/test_dispatch.py` | TOOL_NAME + JSON I/O |
| `tools/structural-anchor/tests/test_integration.py` | End-to-end on fixture + this repo |
| `tools/structural-anchor/examples/sample_input.json` | Example stdin |
| `tools/structural-anchor/README.md` | Install, tools, cache, perf |
| `plugins/structural-anchor.json` | Three tool entries + optional init rule |
| `adapters/structural-anchor/AGENTS.md` | Compact fallback for init rule |
| `registry.json` | Register plugin |

---

### Task 1: Walk + fingerprint helpers (TDD)

**Files:**
- Create: `tools/structural-anchor/structural_anchor.py`
- Create: `tools/structural-anchor/tests/test_walk.py`
- Create: `tools/structural-anchor/tests/conftest.py` (optional empty / path helper)

**Interfaces:**
- Produces:
  - `DEFAULT_SKIP_DIRS: set[str]`
  - `iter_source_files(root: Path, depth: int, skip_dirs: set[str]) -> list[Path]` — returns `.py`/`.go` only; hard depth clip; skips `skip_dirs` and dirs starting with `.`
  - `fingerprint(root: Path) -> str` — HEAD hash, else `.git/index` mtime string, else top-level mtime hash
  - `git_commit(root: Path) -> str | None` — HEAD or None

- [ ] **Step 1: Write failing tests**

```python
# tools/structural-anchor/tests/test_walk.py
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from structural_anchor import iter_source_files, DEFAULT_SKIP_DIRS


def test_iter_respects_depth_and_extensions(tmp_path: Path):
    (tmp_path / "a.py").write_text("x=1\n")
    (tmp_path / "b.go").write_text("package main\n")
    (tmp_path / "c.txt").write_text("nope\n")
    sub = tmp_path / "d1" / "d2" / "d3"
    sub.mkdir(parents=True)
    (sub / "deep.py").write_text("y=1\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.py").write_text("z=1\n")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "h.py").write_text("h=1\n")

    files = {p.relative_to(tmp_path).as_posix() for p in iter_source_files(tmp_path, depth=2, skip_dirs=DEFAULT_SKIP_DIRS)}
    assert "a.py" in files
    assert "b.go" in files
    assert "c.txt" not in files
    assert "d1/d2/d3/deep.py" not in files  # depth 2 hard stop (root=0)
    assert "node_modules/x.py" not in files
    assert ".hidden/h.py" not in files
```

Depth convention: `root_path` is depth 0; immediate children are depth 1; do not descend into a directory when current depth would exceed `depth`. Document this in a one-line comment above `iter_source_files`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/structural-anchor && python3 -m pytest tests/test_walk.py -v`  
Expected: FAIL (import or missing function)

- [ ] **Step 3: Minimal implementation**

Add to `structural_anchor.py`:

```python
#!/usr/bin/env python3
"""structural-anchor: codebase map for naitv-mcp (JSON stdin/stdout)."""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

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
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd tools/structural-anchor && python3 -m pytest tests/test_walk.py -v`  
Expected: PASS

- [ ] **Step 5: Commit (jj)**

```bash
jj commit -m "feat(structural-anchor): add depth-limited source walk and fingerprint"
```

---

### Task 2: Python symbol extraction + complexity

**Files:**
- Modify: `tools/structural-anchor/structural_anchor.py`
- Create: `tools/structural-anchor/tests/test_python_symbols.py`
- Create: `tools/structural-anchor/tests/fixtures/sample.py`

**Interfaces:**
- Produces:
  - `Symbol` dict shape: `{name, kind, signature, line}`
  - `extract_python_symbols(path: Path) -> tuple[list[dict], list[float], int]` → (symbols, per-function complexities, line_count) or raises/`None` on parse error handled by caller
  - `cyclomatic_python(node: ast.AST) -> float` — decision nodes + 1

- [ ] **Step 1: Write fixture + failing test**

```python
# tools/structural-anchor/tests/fixtures/sample.py
class Greeter:
    def hello(self, name: str) -> str:
        if name:
            return f"hi {name}"
        return "hi"


def add(a: int, b: int) -> int:
    return a + b
```

```python
# tools/structural-anchor/tests/test_python_symbols.py
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from structural_anchor import extract_python_symbols

FIX = Path(__file__).parent / "fixtures" / "sample.py"


def test_extract_python_symbols():
    symbols, complexities, lines = extract_python_symbols(FIX)
    names = {(s["name"], s["kind"]) for s in symbols}
    assert ("Greeter", "class") in names
    assert ("hello", "method") in names
    assert ("add", "function") in names
    assert lines > 0
    assert all(c >= 1 for c in complexities)
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd tools/structural-anchor && python3 -m pytest tests/test_python_symbols.py -v`

- [ ] **Step 3: Implement**

```python
import ast
from typing import Any


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
```

- [ ] **Step 4: Run — expect PASS**

Run: `cd tools/structural-anchor && python3 -m pytest tests/test_python_symbols.py -v`

- [ ] **Step 5: Commit (jj)**

```bash
jj commit -m "feat(structural-anchor): extract Python symbols and complexity"
```

---

### Task 3: Go `go_symbols` helper

**Files:**
- Create: `tools/structural-anchor/go_symbols/go.mod`
- Create: `tools/structural-anchor/go_symbols/main.go`
- Create: `tools/structural-anchor/go_symbols/main_test.go`
- Create: `tools/structural-anchor/go_symbols/testdata/sample.go`

**Interfaces:**
- Consumes: stdin JSON `{"files":["/abs/a.go",...]}`
- Produces: stdout JSON `{"packages":[{"name":"pkg","path":"rel/or/dir","symbols":[...]}],"errors":N}`
  - kinds: `function`, `method`, `type`, `interface`, `const`, `var` (exported only for const/var)
- Complexity: include optional `"complexities":[float,...]` at top level for Python to merge, OR embed per-function in a parallel array — **use top-level** `complexities` list of floats aligned with functions/methods only (document in README). Simpler: each function/method symbol may omit complexity; helper returns `"func_complexity": [..]` list. **Spec:** helper returns `func_complexity: []float64` for every function/method in visit order.

- [ ] **Step 1: Write testdata + Go test**

```go
// tools/structural-anchor/go_symbols/testdata/sample.go
package sample

type Greeter struct{}

func (g Greeter) Hello(name string) string { return name }

func Add(a, b int) int {
	if a > 0 {
		return a + b
	}
	return b
}

type Face interface {
	Hello(string) string
}

const Exported = 1

var ExportedVar = 2
```

```go
// tools/structural-anchor/go_symbols/main_test.go
package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestExtractSample(t *testing.T) {
	path := filepath.Join("testdata", "sample.go")
	abs, _ := filepath.Abs(path)
	out, err := extract([]string{abs})
	if err != nil {
		t.Fatal(err)
	}
	if len(out.Packages) == 0 {
		t.Fatal("no packages")
	}
	kinds := map[string]string{}
	for _, s := range out.Packages[0].Symbols {
		kinds[s.Name] = s.Kind
	}
	if kinds["Add"] != "function" || kinds["Hello"] != "method" {
		t.Fatalf("kinds=%v", kinds)
	}
	if kinds["Greeter"] != "type" || kinds["Face"] != "interface" {
		t.Fatalf("types=%v", kinds)
	}
	if kinds["Exported"] != "const" || kinds["ExportedVar"] != "var" {
		t.Fatalf("vars=%v", kinds)
	}
	_ = json.NewEncoder(os.Stdout)
}
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd tools/structural-anchor/go_symbols && go test ./...`  
Expected: FAIL (undefined extract)

- [ ] **Step 3: Implement `main.go`**

```go
package main

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"strings"
	"unicode"
	"unicode/utf8"
)

type Symbol struct {
	Name      string `json:"name"`
	Kind      string `json:"kind"`
	Signature string `json:"signature"`
	Line      int    `json:"line"`
}

type Package struct {
	Name    string   `json:"name"`
	Path    string   `json:"path"`
	Symbols []Symbol `json:"symbols"`
}

type Result struct {
	Packages       []Package `json:"packages"`
	FuncComplexity []float64 `json:"func_complexity"`
	Errors         int       `json:"errors"`
}

type input struct {
	Files []string `json:"files"`
}

func isExported(name string) bool {
	r, _ := utf8.DecodeRuneInString(name)
	return unicode.IsUpper(r)
}

func cyclomatic(n ast.Node) float64 {
	d := 0
	ast.Inspect(n, func(x ast.Node) bool {
		switch x.(type) {
		case *ast.IfStmt, *ast.ForStmt, *ast.RangeStmt, *ast.CaseClause, *ast.CommClause:
			d++
		}
		return true
	})
	return float64(d + 1)
}

func extract(files []string) (Result, error) {
	fset := token.NewFileSet()
	byDir := map[string][]*ast.File{}
	pkgName := map[string]string{}
	errs := 0
	for _, f := range files {
		af, err := parser.ParseFile(fset, f, nil, 0)
		if err != nil {
			errs++
			continue
		}
		dir := filepath.Dir(f)
		byDir[dir] = append(byDir[dir], af)
		pkgName[dir] = af.Name.Name
	}
	var res Result
	res.Errors = errs
	for dir, filesAst := range byDir {
		pkg := Package{Name: pkgName[dir], Path: dir, Symbols: nil}
		for _, af := range filesAst {
			for _, decl := range af.Decls {
				switch d := decl.(type) {
				case *ast.FuncDecl:
					kind := "function"
					sig := "func " + d.Name.Name
					if d.Recv != nil {
						kind = "method"
					}
					line := fset.Position(d.Pos()).Line
					pkg.Symbols = append(pkg.Symbols, Symbol{Name: d.Name.Name, Kind: kind, Signature: sig, Line: line})
					res.FuncComplexity = append(res.FuncComplexity, cyclomatic(d))
				case *ast.GenDecl:
					for _, spec := range d.Specs {
						switch s := spec.(type) {
						case *ast.TypeSpec:
							kind := "type"
							if _, ok := s.Type.(*ast.InterfaceType); ok {
								kind = "interface"
							}
							if !isExported(s.Name.Name) {
								continue
							}
							line := fset.Position(s.Pos()).Line
							pkg.Symbols = append(pkg.Symbols, Symbol{Name: s.Name.Name, Kind: kind, Signature: kind + " " + s.Name.Name, Line: line})
						case *ast.ValueSpec:
							kind := "var"
							if d.Tok.String() == "const" {
								kind = "const"
							}
							for _, name := range s.Names {
								if !isExported(name.Name) {
									continue
								}
								line := fset.Position(name.Pos()).Line
								pkg.Symbols = append(pkg.Symbols, Symbol{Name: name.Name, Kind: kind, Signature: kind + " " + name.Name, Line: line})
							}
						}
					}
				}
			}
		}
		res.Packages = append(res.Packages, pkg)
	}
	return res, nil
}

func main() {
	var in input
	if err := json.NewDecoder(os.Stdin).Decode(&in); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	out, err := extract(in.Files)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if err := json.NewEncoder(os.Stdout).Encode(out); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

// silence unused in case of trim
var _ = strings.TrimSpace
```

Also create `go.mod`:

```
module github.com/madicen/naitv-mcp-plugins/tools/structural-anchor/go_symbols

go 1.21
```

Improve function signatures in a follow-up only if tests need them; for v1 `func Name` / `method` is acceptable if line+kind are correct — prefer adding `types.ExprString`-free simple recv using `ast.Inspect` only if easy. Minimum: include receiver in signature string via `fmt` of type if present.

- [ ] **Step 4: Run — expect PASS**

Run: `cd tools/structural-anchor/go_symbols && go test ./...`  
Expected: PASS

- [ ] **Step 5: Commit (jj)**

```bash
jj commit -m "feat(structural-anchor): add go_symbols helper with go/parser"
```

---

### Task 4: Cache + ensure Go binary

**Files:**
- Modify: `tools/structural-anchor/structural_anchor.py`
- Create: `tools/structural-anchor/tests/test_cache.py`

**Interfaces:**
- Produces:
  - `cache_dir() -> Path` → `~/.cache/naitv-mcp/structural-anchor`
  - `cache_key(root, depth, skip_dirs, fp) -> str`
  - `load_cache(key) -> dict | None`
  - `save_cache(key, payload: dict) -> None`
  - `ensure_go_symbols_bin(src_dir: Path) -> Path | None` — builds to `~/.cache/naitv-mcp/bin/go-symbols` or returns None

- [ ] **Step 1: Failing test**

```python
# tools/structural-anchor/tests/test_cache.py
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from structural_anchor import cache_key, load_cache, save_cache, cache_dir


def test_cache_roundtrip(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))
    key = cache_key(Path("/repo"), 3, {"vendor"}, "abc")
    assert load_cache(key) is None
    save_cache(key, {"packages": [], "languages": [], "statistics": {}})
    assert load_cache(key)["packages"] == []
    assert (cache_dir() / f"{key}.json").is_file()
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement**

```python
import json
from typing import Any


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
    r = subprocess.run(
        ["go", "build", "-o", str(out), "."],
        cwd=src_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode != 0:
        return None
    return out if out.is_file() else None
```

- [ ] **Step 4: Run — expect PASS**

Run: `cd tools/structural-anchor && python3 -m pytest tests/test_cache.py -v`

- [ ] **Step 5: Commit (jj)**

```bash
jj commit -m "feat(structural-anchor): add map cache and go-symbols binary ensure"
```

---

### Task 5: Build map + tool projections + main()

**Files:**
- Modify: `tools/structural-anchor/structural_anchor.py`
- Create: `tools/structural-anchor/tests/test_dispatch.py`
- Create: `tools/structural-anchor/examples/sample_input.json`

**Interfaces:**
- Produces:
  - `build_project_map(root, depth, skip_dirs) -> dict` (uncached payload without `cached`)
  - `get_project_map(...)`, `list_languages(...)`, `get_codebase_statistics(...)`
  - `main()` reads stdin JSON + `TOOL_NAME`

Package grouping:
- Python: package `path` = parent dir relative to root (`./` → `.`); `name` = dir name or file stem for lone modules at root
- Go: use helper package name + path relative to root when possible

Parallel Python: `concurrent.futures.ThreadPoolExecutor(max_workers=8)`.

- [ ] **Step 1: Failing dispatch test**

```python
# tools/structural-anchor/tests/test_dispatch.py
import json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / "fixtures"


def test_get_project_map_cli(tmp_path: Path):
    # copy fixture tree
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text("def f():\n    return 1\n")
    env = os.environ.copy()
    env["TOOL_NAME"] = "get_project_map"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "structural_anchor.py")],
        input=json.dumps({"root_path": str(tmp_path), "depth": 5}) + "\n",
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert "packages" in out and "statistics" in out
    assert out.get("cached") is False
```

```json
{"root_path": ".", "depth": 3}
```
→ save as `examples/sample_input.json` (path filled by caller).

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement build + main**

Implement in `structural_anchor.py` (keep functions flat; no new abstraction layers):

1. `build_project_map` walks files; partitions `.py` / `.go`.
2. Thread-pool Python extracts; accumulate symbols into `dict[str, package]`.
3. `ensure_go_symbols_bin` using `Path(__file__).parent / "go_symbols"`; if bin exists, `subprocess.run([bin], input=json.dumps({"files": go_files}))`; merge packages; add `func_complexity` into go complexities list; on failure warn stderr and continue.
4. Compute statistics:
   - `total_files`, `total_lines`, `packages`, `parse_errors`
   - `by_language`: files/lines/complexity mean
   - top-level `complexity` = mean of all function complexities (0 if empty)
5. `languages` sorted unique ids present.
6. Attach `commit` if `git_commit(root)`.
7. Tool wrappers load/save cache; set `cached` True/False.
8. `list_languages` projects from map; `primary` = max file_count.
9. `get_codebase_statistics` returns statistics + cached + optional commit.
10. `main()`:

```python
def main() -> None:
    tool = os.environ.get("TOOL_NAME", "").strip()
    try:
        data = json.loads(sys.stdin.readline())
    except Exception as e:
        print(f"invalid JSON: {e}", file=sys.stderr)
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
```

- [ ] **Step 4: Run unit + dispatch tests**

Run: `cd tools/structural-anchor && python3 -m pytest tests/ -v --ignore=tests/test_integration.py`  
Expected: PASS

- [ ] **Step 5: Commit (jj)**

```bash
jj commit -m "feat(structural-anchor): build project map and TOOL_NAME dispatch"
```

---

### Task 6: Plugin JSON, registry, adapter, README

**Files:**
- Create: `plugins/structural-anchor.json`
- Create: `adapters/structural-anchor/AGENTS.md`
- Create: `tools/structural-anchor/README.md`
- Modify: `registry.json`
- Modify: `README.md` (add row to plugins table if one exists)

**Interfaces:**
- Three tool entries with B1 exec + `io_mode=json`
- Optional init rule: prefer structural-anchor before thrashing

- [ ] **Step 1: Write `plugins/structural-anchor.json`**

```json
{
  "name": "structural-anchor",
  "version": "1.0.0",
  "description": "Codebase structural map — packages, symbols, languages, and stats (Python + Go) for naitv-mcp agents.",
  "author": "madicen",
  "tags": ["structural-anchor", "context", "codebase-map"],
  "entries": [
    {
      "kind": "rule",
      "name": "prefer-structural-anchor",
      "delivery": "init",
      "tags": ["structural-anchor"],
      "body": "Before broad greps or opening many files to learn a repo, call get_project_map (or list_languages / get_codebase_statistics) from structural-anchor with root_path set to the project root. Use the returned packages/symbols map to orient; only then open specific files."
    },
    {
      "kind": "tool",
      "name": "get_project_map",
      "delivery": "on-demand",
      "tags": ["structural-anchor"],
      "body": "Build a flattened map of packages and symbols (Python + Go) for root_path. Cached per commit fingerprint under ~/.cache/naitv-mcp/.",
      "fields": {
        "exec": "TOOL_NAME=get_project_map python3 ~/.config/naitv-mcp/tools/structural-anchor/structural_anchor.py",
        "io_mode": "json",
        "timeout": "30s",
        "params": "[{\"name\":\"root_path\",\"description\":\"Absolute path to the project root\",\"required\":true},{\"name\":\"depth\",\"description\":\"Max directory walk depth (default 3)\",\"required\":false},{\"name\":\"skip_dirs\",\"description\":\"Directory basenames to prune\",\"required\":false}]"
      }
    },
    {
      "kind": "tool",
      "name": "list_languages",
      "delivery": "on-demand",
      "tags": ["structural-anchor"],
      "body": "Detect programming languages (file/line counts) under root_path. Shares cache with get_project_map.",
      "fields": {
        "exec": "TOOL_NAME=list_languages python3 ~/.config/naitv-mcp/tools/structural-anchor/structural_anchor.py",
        "io_mode": "json",
        "timeout": "30s",
        "params": "[{\"name\":\"root_path\",\"description\":\"Absolute path to the project root\",\"required\":true},{\"name\":\"depth\",\"description\":\"Max directory walk depth (default 3)\",\"required\":false},{\"name\":\"skip_dirs\",\"description\":\"Directory basenames to prune\",\"required\":false}]"
      }
    },
    {
      "kind": "tool",
      "name": "get_codebase_statistics",
      "delivery": "on-demand",
      "tags": ["structural-anchor"],
      "body": "Return size and approximate complexity metrics for root_path. Shares cache with get_project_map.",
      "fields": {
        "exec": "TOOL_NAME=get_codebase_statistics python3 ~/.config/naitv-mcp/tools/structural-anchor/structural_anchor.py",
        "io_mode": "json",
        "timeout": "30s",
        "params": "[{\"name\":\"root_path\",\"description\":\"Absolute path to the project root\",\"required\":true},{\"name\":\"depth\",\"description\":\"Max directory walk depth (default 3)\",\"required\":false},{\"name\":\"skip_dirs\",\"description\":\"Directory basenames to prune\",\"required\":false}]"
      }
    }
  ]
}
```

- [ ] **Step 2: Adapter + README + registry**

`adapters/structural-anchor/AGENTS.md` — distill the init rule to one screen; note canonical source is `plugins/structural-anchor.json`.

`tools/structural-anchor/README.md` — install (`mkdir -p ~/.config/naitv-mcp/tools && ln -s $(pwd)/tools/structural-anchor ~/.config/naitv-mcp/tools/structural-anchor`), TOOL_NAME, cache paths, examples, Go optional.

`registry.json` — append plugin entry pointing at raw GitHub URL like existing plugins.

- [ ] **Step 3: Sanity-check JSON**

Run: `python3 -c "import json; json.load(open('plugins/structural-anchor.json'))"`  
Expected: no error

- [ ] **Step 4: Commit (jj)**

```bash
jj commit -m "feat(structural-anchor): add plugin JSON, registry, adapter, README"
```

---

### Task 7: Integration + cache-hit + soft smoke

**Files:**
- Create: `tools/structural-anchor/tests/test_integration.py`

- [ ] **Step 1: Write integration tests**

```python
# tools/structural-anchor/tests/test_integration.py
import json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]  # naitv-mcp-plugins root


def _run(tool: str, payload: dict, env_home: str | None = None):
    env = os.environ.copy()
    env["TOOL_NAME"] = tool
    if env_home:
        env["HOME"] = env_home
    return subprocess.run(
        [sys.executable, str(ROOT / "structural_anchor.py")],
        input=json.dumps(payload) + "\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_this_repo_map(tmp_path: Path):
    p1 = _run("get_project_map", {"root_path": str(REPO), "depth": 4}, env_home=str(tmp_path))
    assert p1.returncode == 0, p1.stderr
    out1 = json.loads(p1.stdout)
    assert out1["cached"] is False
    assert isinstance(out1["packages"], list)
    p2 = _run("get_project_map", {"root_path": str(REPO), "depth": 4}, env_home=str(tmp_path))
    assert p2.returncode == 0
    out2 = json.loads(p2.stdout)
    assert out2["cached"] is True


def test_perf_smoke_many_tiny_files(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    tree = tmp_path / "tree"
    tree.mkdir()
    for i in range(500):
        d = tree / f"p{i % 50}"
        d.mkdir(exist_ok=True)
        (d / f"f{i}.py").write_text(f"def f{i}():\n    return {i}\n")
    t0 = time.perf_counter()
    proc = _run("get_project_map", {"root_path": str(tree), "depth": 5}, env_home=str(home))
    elapsed = time.perf_counter() - t0
    assert proc.returncode == 0, proc.stderr
    assert elapsed < 5.0  # soft CI budget; design target <2s on prune-heavy 50k
```

- [ ] **Step 2: Run full suite**

Run: `cd tools/structural-anchor && python3 -m pytest tests/ -v && cd go_symbols && go test ./...`  
Expected: all PASS

- [ ] **Step 3: Manual local demo (optional)**

```bash
ln -sfn "$(pwd)/tools/structural-anchor" ~/.config/naitv-mcp/tools/structural-anchor
TOOL_NAME=get_project_map python3 tools/structural-anchor/structural_anchor.py <<'EOF'
{"root_path":"/Users/michael.madicen/Documents/GitHub/naitv-mcp-plugins","depth":3}
EOF
```

- [ ] **Step 4: Commit (jj)**

```bash
jj commit -m "test(structural-anchor): integration, cache hit, and perf smoke"
```

---

## Self-review (plan vs spec)

| Spec item | Task |
|-----------|------|
| B1 TOOL_NAME dispatch | 5, 6 |
| Three tools only | 5, 6 |
| Python ast + Go helper | 2, 3, 5 |
| Depth hard stop | 1 |
| Cache + commit omit | 4, 5 |
| Per-language + global complexity | 5 |
| Plugin JSON + registry | 6 |
| Tests (unit/integration/golden) | 1–5, 3, 7 |
| No validate_structure / no TS | Global + omitted |
| jj per-task commits | every Step 5 |

No TBD placeholders. Go signature richness is minimal but kinds/lines covered; Python signatures include args/returns.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-12-structural-anchor.md`.

**Version control note:** every task commit uses `jj commit -m "…"` (not git). A naitv rule proposal `use-jj-for-naitv-mcp-plugins` is queued for TUI approval.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — execute in this session with executing-plans checkpoints  

Which approach?
