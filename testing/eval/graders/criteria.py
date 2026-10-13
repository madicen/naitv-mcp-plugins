from __future__ import annotations

import re
from typing import Any


def grade_success(answer: str, success: dict[str, Any]) -> dict[str, Any]:
    """Apply a machine-checkable success criterion to the final answer text."""
    kind = success.get("type")
    text = answer or ""
    lowered = text.lower()

    if kind == "answer_contains_all":
        values = [str(v) for v in success.get("values", [])]
        missing = [v for v in values if v.lower() not in lowered]
        return {
            "passed": not missing,
            "kind": kind,
            "missing": missing,
        }

    if kind == "answer_regex":
        pattern = success.get("pattern", "")
        matched = bool(re.search(pattern, text, re.IGNORECASE | re.MULTILINE))
        return {"passed": matched, "kind": kind, "pattern": pattern}

    return {"passed": False, "kind": kind or "unknown", "error": "unsupported success type"}
