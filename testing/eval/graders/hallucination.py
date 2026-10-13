from __future__ import annotations

import re
from typing import Any

# Code-like identifiers only: CamelCase / snake_case (not plain English words).
_IDENT = re.compile(
    r"\b([A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+|[A-Z][a-zA-Z0-9]{2,}|[a-z]+_[a-z0-9_]+)\b"
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


def grade_hallucination(answer: str, project_map: dict[str, Any]) -> dict[str, Any]:
    candidates = extract_candidate_symbols(answer)
    real = real_symbol_names(project_map)
    # Also accept path basenames without extension as real-ish (greeter from greeter.py)
    for pkg in project_map.get("packages") or []:
        path = str(pkg.get("path", ""))
        for part in path.split("/"):
            if part:
                real.add(part)

    missing = [c for c in candidates if c not in real and c.lower() not in {r.lower() for r in real}]
    rate = (len(missing) / len(candidates)) if candidates else 0.0
    return {
        "candidates": candidates,
        "nonexistent": missing,
        "nonexistent_rate": rate,
        "real_symbol_count": len(real),
    }
