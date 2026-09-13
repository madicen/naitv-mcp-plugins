from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from symbol_navigator import extract_python_defs, find_python_refs


def test_python_refs_finds_call_not_def():
    path = Path(__file__).parent / "fixtures" / "refs_sample.py"
    defs = extract_python_defs(path)
    greeter = next(d for d in defs if d["name"] == "Greeter")
    refs = find_python_refs(path, "Greeter", exclude_line=greeter["line"])
    assert any(r["line"] != greeter["line"] for r in refs)
    assert any("Greeter" in r["context"] for r in refs)
