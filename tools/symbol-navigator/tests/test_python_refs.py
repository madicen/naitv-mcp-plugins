from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from symbol_navigator import extract_python_defs, find_python_refs, get_symbol_references


def test_python_refs_finds_call_not_def():
    path = Path(__file__).parent / "fixtures" / "refs_sample.py"
    defs = extract_python_defs(path)
    greeter = next(d for d in defs if d["name"] == "Greeter")
    refs = find_python_refs(path, "Greeter", exclude_line=greeter["line"])
    assert any(r["line"] != greeter["line"] for r in refs)
    assert any("Greeter" in r["context"] for r in refs)


def test_references_keep_same_line_use_when_def_excluded_by_column(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("HOME", str(tmp_path))
    fixture = Path(__file__).parent / "fixtures" / "same_line_refs.py"
    root = tmp_path / "proj"
    root.mkdir()
    (root / "same_line_refs.py").write_text(fixture.read_text(encoding="utf-8"))

    result = get_symbol_references(root, 2, set(), "Foo")
    refs = result["references"]
    assert len(refs) == 1
    assert refs[0]["line"] == result["definition"]["line"]
    assert refs[0]["column"] != result["definition"]["column"]
    assert "Foo()" in refs[0]["context"]
