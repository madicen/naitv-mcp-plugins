#!/usr/bin/env python3
"""L1 structural lint for plugin manifests (rules-only and mixed)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "testing"))

from plugin_harness import load_manifest  # noqa: E402

VALID_KINDS = frozenset({"rule", "workflow", "fact", "note", "tool", "project"})
VALID_DELIVERY = frozenset({"init", "on-demand", "review", ""})


def lint(name: str) -> int:
    manifest = load_manifest(name)
    failures = 0
    if manifest.get("name") and manifest["name"] != name:
        print(f"FAIL name mismatch: manifest={manifest['name']!r} dir={name!r}")
        failures += 1
    entries = manifest.get("entries") or []
    if not entries:
        print("FAIL no entries")
        failures += 1
    seen: dict[str, str] = {}
    for i, entry in enumerate(entries):
        kind = entry.get("kind", "")
        ename = entry.get("name", "")
        label = f"entries[{i}]/{ename or '?'}"
        if kind not in VALID_KINDS:
            print(f"FAIL {label}: bad kind {kind!r}")
            failures += 1
        if not ename:
            print(f"FAIL {label}: missing name")
            failures += 1
        elif ename in seen:
            print(f"FAIL duplicate entry name {ename!r}")
            failures += 1
        else:
            seen[ename] = label
        delivery = entry.get("delivery") or ""
        if delivery and delivery not in VALID_DELIVERY:
            print(f"FAIL {label}: bad delivery {delivery!r}")
            failures += 1
        if kind == "tool":
            fields = entry.get("fields") or {}
            if not fields.get("exec"):
                print(f"FAIL {label}: tool missing fields.exec")
                failures += 1
            io_mode = fields.get("io_mode") or "text"
            if io_mode not in ("json", "JSON", "text", "TEXT"):
                print(f"FAIL {label}: bad io_mode {io_mode!r}")
                failures += 1
            # JSON tools need schemas later (L2); text tools use working_dir / stdout text.
        body = entry.get("body")
        if body is None or (isinstance(body, str) and not body.strip()):
            print(f"FAIL {label}: empty body")
            failures += 1
        else:
            print(f"PASS {label}")
    print(f"Summary: failures={failures} entries={len(entries)}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plugin")
    args = parser.parse_args()
    try:
        return lint(args.plugin)
    except FileNotFoundError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
