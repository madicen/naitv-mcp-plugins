from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from symbol_navigator import extract_python_defs

FIX = Path(__file__).parent / "fixtures" / "sample.py"


def test_extract_python_defs_nested_and_signatures():
    defs = extract_python_defs(FIX)
    by = {(d["name"], d["kind"]): d for d in defs}
    assert ("Outer", "class") in by
    assert ("Inner", "class") in by
    assert ("nested", "method") in by
    assert ("method", "method") in by
    assert ("top", "function") in by
    assert "a: int" in by[("method", "method")]["signature"]
    assert "*rest" in by[("method", "method")]["signature"]
    assert "os" in by[("top", "function")]["imports"] or "os" in defs[0]["imports"]
    assert "os" in by[("top", "function")]["imports"]
