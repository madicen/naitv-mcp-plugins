from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from structural_anchor import extract_python_symbols

FIX = Path(__file__).parent / "fixtures" / "sample.py"


def test_extract_python_symbols():
    symbols, complexities, lines = extract_python_symbols(FIX)
    names = {(s["name"], s["kind"]) for s in symbols}
    assert ("Greeter", "class") in names
    assert ("hello", "method") in names
    assert ("add", "function") in names
    assert lines > 0
    assert all(c >= 1 for c in complexities)
