from graders.criteria import grade_success
from graders.hallucination import grade_hallucination


def test_answer_contains_all() -> None:
    got = grade_success(
        "Greeter is a class in pkg/greeter.py",
        {"type": "answer_contains_all", "values": ["Greeter", "greeter.py", "class"]},
    )
    assert got["passed"] is True


def test_hallucination_flags_unknown_symbol() -> None:
    pmap = {
        "packages": [
            {
                "name": "pkg",
                "path": "pkg",
                "symbols": [{"name": "Greeter", "kind": "class"}],
            }
        ],
        "languages": ["python"],
    }
    got = grade_hallucination("Greeter and TotallyFakeService are used", pmap)
    assert "TotallyFakeService" in got["nonexistent"]
    assert "Greeter" not in got["nonexistent"]


def test_hallucination_ignores_allcaps_and_title_english() -> None:
    pmap = {"packages": [{"name": "pkg", "path": "pkg", "symbols": []}], "languages": ["python"]}
    got = grade_hallucination("README Final Path Makefile FAIL yes", pmap)
    assert got["nonexistent"] == []
    assert got["candidates"] == []


def test_hallucination_accepts_file_stems() -> None:
    pmap = {
        "packages": [
            {
                "name": "greeter",
                "path": "pkg/greeter",
                "symbols": [{"name": "FuzzHello", "path": "pkg/greeter/greeter_fuzz_test.go"}],
            }
        ],
        "languages": ["go"],
    }
    got = grade_hallucination("see greeter_fuzz_test and mod_a missing", pmap)
    assert "greeter_fuzz_test" not in got["nonexistent"]
    assert "mod_a" in got["nonexistent"]
