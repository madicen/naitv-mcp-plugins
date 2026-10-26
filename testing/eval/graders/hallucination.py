from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

# True CamelCase (Greeter, FakeService) or snake_case (mod_a, get_map).
# Deliberately excludes ALLCAPS (README, FAIL) and single Title-case English (Final, Path).
_IDENT = re.compile(
    r"\b([A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+|[a-z]+_[a-z0-9_]+)\b"
)
_STOP = frozenset(
    {
        "Greeter",  # real in fixtures — kept via project map anyway
        "Primary",
        "Languages",
        "Exported",
        "Include",
        "Includes",
        "Matched",
        "Results",
        "Symbols",
        "Found",
        "The",
        "Users",
        "Documents",
        "GitHub",
        # common JSON / report field names (not code symbols)
        "node_count",
        "edge_count",
        "fan_in",
        "fan_out",
        "exit_code",
        "build_system",
        "config_files",
        "file_count",
        "line_count",
        "should_skip_test",
        "baseline_skip",
    }
)


def extract_candidate_symbols(text: str) -> list[str]:
    found: list[str] = []
    for match in _IDENT.finditer(text or ""):
        token = match.group(1)
        if token in _STOP or token.lower() in {s.lower() for s in _STOP}:
            continue
        if token not in found:
            found.append(token)
    return found


def real_symbol_names(project_map: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for pkg in project_map.get("packages") or []:
        names.add(str(pkg.get("name", "")))
        for sym in pkg.get("symbols") or []:
            names.add(str(sym.get("name", "")))
    names.discard("")
    # Language ids are not hallucinations when mentioned.
    for lang in project_map.get("languages") or []:
        names.add(str(lang))
    return names


def _add_path_tokens(real: set[str], path: str) -> None:
    for part in path.replace("\\", "/").split("/"):
        if not part or part in {".", ".."}:
            continue
        real.add(part)
        stem = PurePosixPath(part).stem
        if stem:
            real.add(stem)


def grade_hallucination(
    answer: str,
    project_map: dict[str, Any],
    *,
    extra_allowed: set[str] | None = None,
) -> dict[str, Any]:
    candidates = extract_candidate_symbols(answer)
    real = real_symbol_names(project_map)
    # Accept path segments and file stems (greeter_fuzz_test from greeter_fuzz_test.go).
    for pkg in project_map.get("packages") or []:
        _add_path_tokens(real, str(pkg.get("path", "")))
        for sym in pkg.get("symbols") or []:
            _add_path_tokens(real, str(sym.get("path", "") or ""))
    if extra_allowed:
        real |= {str(x) for x in extra_allowed if x}

    missing = [c for c in candidates if c not in real and c.lower() not in {r.lower() for r in real}]
    rate = (len(missing) / len(candidates)) if candidates else 0.0
    return {
        "candidates": candidates,
        "nonexistent": missing,
        "nonexistent_rate": rate,
        "real_symbol_count": len(real),
    }
