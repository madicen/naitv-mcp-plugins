"""Shared grounded scan helpers for generated JSON I/O tools (stdlib only)."""
from __future__ import annotations

import os
import re
from pathlib import Path

MAX_FILES = 500
MAX_FILE_BYTES = 64_000
SKIP = {".git", "node_modules", "vendor", ".venv", "__pycache__", "dist", "build"}

# Identifiers from source — regex only, no invented names.
_PY_DEF = re.compile(
    r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
_GO_DEF = re.compile(
    r"^\s*func\s+(?:\([^)]+\)\s*)?([A-Za-z_][A-Za-z0-9_]*)|"
    r"^\s*type\s+([A-Za-z_][A-Za-z0-9_]*)|"
    r"^\s*(?:const|var)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
_ENV_KEY = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", re.MULTILINE)
_PY_IMPORT = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
    re.MULTILINE,
)
_GO_IMPORT = re.compile(r'^\s*"([^"]+)"\s*$', re.MULTILINE)
_LOG_CALL = re.compile(
    r"\b(?:logging\.(?:debug|info|warning|error|critical|exception)|"
    r"logger\.(?:debug|info|warning|error|critical|exception)|"
    r"log\.(?:Print|Printf|Println|Fatal|Fatalf|Panic|Panicf)|"
    r"fmt\.Print(?:ln|f)?|print\s*\()",
    re.IGNORECASE,
)
_SECRETISH = re.compile(
    r"(?i)(password|secret|api[_-]?key|token|private[_-]?key|"
    r"aws_access|database_url)\s*[=:]",
)


def validate_root_path(root: str, *, error) -> Path:
    """Resolve root_path; call error(msg) on failure (typically prints + exits)."""
    raw = Path(root)
    if ".." in raw.parts:
        error(f"root_path must not contain '..': {root}")
    path = raw.expanduser()
    path = path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
    if not path.exists():
        error(f"root_path does not exist: {root}")
    if not path.is_dir():
        error(f"root_path is not a directory: {root}")
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
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return path.name


def read_text(path: Path) -> str:
    try:
        data = path.read_bytes()[:MAX_FILE_BYTES]
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")


def extract_identifiers(text: str, suffix: str = "") -> list[str]:
    """Return real def/class/func/type/const names from source text."""
    names: list[str] = []
    seen: set[str] = set()
    suf = suffix.lower()

    def add(n: str | None) -> None:
        if not n or n in seen:
            return
        seen.add(n)
        names.append(n)

    if suf in {".py", ".pyi"} or not suf:
        for m in _PY_DEF.finditer(text):
            add(m.group(1))
    if suf in {".go"} or not suf:
        for m in _GO_DEF.finditer(text):
            add(next(g for g in m.groups() if g))
    return names


def extract_env_keys(text: str) -> list[str]:
    return list(dict.fromkeys(_ENV_KEY.findall(text)))


def extract_imports(text: str, suffix: str = "") -> list[str]:
    mods: list[str] = []
    seen: set[str] = set()
    suf = suffix.lower()
    if suf in {".py", ".pyi"} or not suf:
        for m in _PY_IMPORT.finditer(text):
            name = m.group(1) or m.group(2)
            if name and name not in seen:
                seen.add(name)
                mods.append(name)
    if suf == ".go" or not suf:
        for m in _GO_IMPORT.finditer(text):
            name = m.group(1)
            if name and name not in seen:
                seen.add(name)
                mods.append(name)
    return mods


def find_log_spans(text: str) -> list[tuple[int, str]]:
    """(1-based line, snippet) for log/print-like calls."""
    out: list[tuple[int, str]] = []
    for m in _LOG_CALL.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        snippet = text[m.start() : m.start() + 60].split("\n", 1)[0]
        out.append((line, snippet))
    return out


def find_secretish(text: str) -> list[tuple[int, str]]:
    """(1-based line, matched key-ish token) — heuristic only."""
    out: list[tuple[int, str]] = []
    for m in _SECRETISH.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        out.append((line, m.group(1)))
    return out


def is_env_path(rel_path: str) -> bool:
    name = Path(rel_path).name.lower()
    return name.startswith(".env") or name.endswith(".env") or name == "env.example"


def is_decision_path(rel_path: str) -> bool:
    low = rel_path.replace("\\", "/").lower()
    name = Path(low).name
    return (
        "/adr/" in f"/{low}"
        or name.startswith("adr-")
        or name in {"decisions.md", "decision-log.md", "architecture-decisions.md"}
    )


def match_query(query: str, rel_path: str, text: str, names: list[str] | None = None) -> bool:
    """True if query is empty or appears in path, text, or extracted names."""
    q = query.strip().lower()
    if not q:
        return True
    if q in rel_path.lower() or q in text.lower():
        return True
    if names and any(q in n.lower() for n in names):
        return True
    return False
