#!/usr/bin/env python3
"""Validate docs/plan/plugins.json (the build-cycle catalog).

Checks: unique kebab-case names, valid status/profile/l5 values, dependencies
exist and are not later phases, planned entries have a tool list, exists
entries have a manifest on disk, needs-spec entries have notes.

Usage: python3 scripts/catalog_check.py [path/to/plugins.json]
Exit 0 when valid, 1 otherwise.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / "docs" / "plan" / "plugins.json"
STATUS = {"exists", "planned", "needs-spec", "blocked"}
PROFILE = {"json_tools", "rules_only", "mixed"}
L5 = {"pending", "measured-helpful", "measured-no-uplift", "not-applicable"}
CATEGORY = {None, "navigation", "structure", "fix-with-tests", "refactor", "multi-file", "control"}
NAME = re.compile(r"^[a-z][a-z0-9-]*$")


def main(argv):
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT
    data = json.loads(path.read_text())
    plugins = data["plugins"]
    errors = []
    warnings = []
    by_name = {}

    for p in plugins:
        name = p.get("name", "")
        if not NAME.match(name):
            errors.append(f"{name!r}: name must be kebab-case")
        if name in by_name:
            errors.append(f"{name}: duplicate entry")
        by_name[name] = p
        if p.get("status") not in STATUS:
            errors.append(f"{name}: bad status {p.get('status')!r}")
        if p.get("profile") not in PROFILE:
            errors.append(f"{name}: bad profile {p.get('profile')!r}")
        if p.get("l5") not in L5:
            errors.append(f"{name}: bad l5 {p.get('l5')!r}")
        if p.get("eval_category") not in CATEGORY:
            errors.append(f"{name}: bad eval_category {p.get('eval_category')!r}")
        if p.get("status") == "planned" and not p.get("tools"):
            errors.append(f"{name}: planned entries need a complete tools list")
        if p.get("status") == "needs-spec" and not p.get("notes"):
            errors.append(f"{name}: needs-spec entries need notes saying what is missing")
        if p.get("status") == "exists" and not (ROOT / "plugins" / name / "plugin.json").exists():
            errors.append(f"{name}: status exists but plugins/{name}/plugin.json is missing")

    for p in plugins:
        for dep in p.get("depends_on", []):
            if dep not in by_name:
                errors.append(f"{p['name']}: depends on unknown plugin {dep!r}")
            elif by_name[dep].get("phase", 0) > p.get("phase", 0):
                # Matrix phase-order exceptions are warnings: the build cycle still refuses
                # to build a plugin until its dependencies are `exists`, so this is a review signal.
                warnings.append(f"{p['name']}: depends on later-phase plugin {dep!r} (see MATRIX_NOTES.md)")

    counts = Counter(p.get("status") for p in plugins)
    print(f"catalog: {len(plugins)} entries  " + "  ".join(f"{k}={counts.get(k, 0)}" for k in sorted(STATUS)))
    for w in warnings:
        print("WARN", w, file=sys.stderr)
    for e in errors:
        print("ERROR", e, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
