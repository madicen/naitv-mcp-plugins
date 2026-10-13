#!/usr/bin/env python3
"""Build a synthetic repo for perf tests. Output is never committed."""
from __future__ import annotations

import argparse
import random
from pathlib import Path


def write_file(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def gen_python(pkg: str, name: str, rng: random.Random) -> str:
    n = rng.randint(1, 4)
    lines = [f'"""Synthetic module {pkg}.{name}."""', ""]
    for i in range(n):
        lines.append(f"def fn_{name}_{i}(x: int) -> int:")
        lines.append(f"    if x > {rng.randint(0, 10)}:")
        lines.append("        return x + 1")
        lines.append("    return x")
        lines.append("")
    return "\n".join(lines)


def gen_go(pkg: str, name: str, rng: random.Random) -> str:
    lines = [f"package {pkg}", ""]
    for i in range(rng.randint(1, 3)):
        lines.append(f"func Fn{name.title()}{i}(x int) int {{")
        lines.append("\tif x > 0 {")
        lines.append("\t\treturn x + 1")
        lines.append("\t}")
        lines.append("\treturn x")
        lines.append("}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=int, required=True, help="number of source files")
    parser.add_argument("--seed", type=int, required=True, help="RNG seed")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "generated-50k",
        help="output directory (default: testing/fixtures/generated-50k)",
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    write_file(out / "README.md", f"# generated fixture\n\nfiles={args.files} seed={args.seed}\n")

    for i in range(args.files):
        lang = "py" if i % 2 == 0 else "go"
        pkg_idx = i % 50
        pkg = f"pkg{pkg_idx:02d}"
        if lang == "py":
            path = out / "python" / pkg / f"mod_{i}.py"
            body = gen_python(pkg, f"m{i}", rng)
            # Stable symbol for L3 perf lookups (symbol-navigator warm gate).
            if i == 0:
                body = 'class PerfAnchor:\n    """perf harness target"""\n\n    def ping(self) -> str:\n        return "ok"\n\n' + body
            write_file(path, body)
        else:
            path = out / "go" / pkg / f"mod_{i}.go"
            write_file(path, gen_go(pkg, f"m{i}", rng))
            if not (out / "go" / "go.mod").exists():
                write_file(out / "go" / "go.mod", "module example.com/generated\n\ngo 1.22\n")

    print(f"wrote {args.files} files under {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
