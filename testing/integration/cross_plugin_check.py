#!/usr/bin/env python3
"""Cross-plugin L4 checks (plan §5): unique tool names; exec path hygiene."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLUGINS = REPO / "plugins"


def load_manifests() -> list[tuple[str, dict]]:
    """Load plugins/<name>/plugin.json only."""
    out: list[tuple[str, dict]] = []
    for path in sorted(PLUGINS.glob("*/plugin.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        out.append((str(path.relative_to(REPO)), data))
    return out


def main() -> int:
    failures = 0
    seen: dict[str, str] = {}
    allowed_outside = (
        "~/.config/naitv-mcp/tools/",
        "$HOME/.config/naitv-mcp/tools/",
    )
    for label, manifest in load_manifests():
        for entry in manifest.get("entries", []):
            if entry.get("kind") != "tool":
                continue
            name = entry.get("name", "")
            if name in seen:
                print(f"FAIL duplicate tool name {name!r}: {seen[name]} and {label}")
                failures += 1
            else:
                seen[name] = label
            fields = entry.get("fields") or {}
            exec_str = fields.get("exec", "")
            if not exec_str:
                continue
            # Allow documented install path under ~/.config/naitv-mcp/tools/<plugin>/
            if any(token in exec_str for token in allowed_outside):
                continue
            # Relative repo tools/ paths also OK for local manifests
            if "tools/" in exec_str or "./" in exec_str:
                continue
            # Absolute paths outside plugin dir are flagged
            if exec_str.startswith("/") and "naitv-mcp" not in exec_str:
                print(f"FAIL {label}/{name}: exec path looks outside plugin/tools: {exec_str}")
                failures += 1

    print(f"tools indexed: {len(seen)}")
    print(f"Summary: failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
