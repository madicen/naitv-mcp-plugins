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


def test_extract_python_defs_indexes_module_and_class_assignments(tmp_path):
    path = tmp_path / "variables.py"
    path.write_text(
        "MODULE_VALUE = 1\n"
        "annotated: str = 'x'\n"
        "\n"
        "class Settings:\n"
        "    CLASS_LIMIT = 10\n"
        "    label: str = 'default'\n"
        "\n"
        "    def method(self):\n"
        "        local = 1\n",
        encoding="utf-8",
    )

    defs = extract_python_defs(path)
    by_name = {definition["name"]: definition for definition in defs}

    assert by_name["MODULE_VALUE"]["kind"] == "const"
    assert by_name["annotated"]["kind"] == "var"
    assert by_name["CLASS_LIMIT"]["kind"] == "const"
    assert by_name["label"]["kind"] == "var"
    assert "local" not in by_name
