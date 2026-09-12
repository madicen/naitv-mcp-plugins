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


def test_signature_includes_all_python_argument_kinds(tmp_path: Path):
    source = tmp_path / "arguments.py"
    source.write_text(
        "def complete(a: int, /, b, *values: str, required: bool, **options: object) -> None:\n"
        "    pass\n"
    )

    symbols, _, _ = extract_python_symbols(source)

    assert symbols[0]["signature"] == (
        "def complete(a: int, /, b, *values: str, required: bool, **options: object) -> None"
    )


def test_nested_classes_and_methods_are_extracted(tmp_path: Path):
    source = tmp_path / "nested.py"
    source.write_text(
        "class Outer:\n"
        "    class Inner:\n"
        "        def method(self):\n"
        "            return 1\n"
    )

    symbols, _, _ = extract_python_symbols(source)

    assert {(symbol["name"], symbol["kind"]) for symbol in symbols} == {
        ("Outer", "class"),
        ("Inner", "class"),
        ("method", "method"),
    }
